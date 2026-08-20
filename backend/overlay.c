#define GLFW_EXPOSE_NATIVE_X11
#include <GL/gl.h>
#include <GLFW/glfw3.h>
#include <GLFW/glfw3native.h>
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

static const char *FLAG = "/tmp/deckvoice_ptt";
static const char *VU = "/tmp/deckvoice_vu";
static float bars[8];

static int flag_on(void) {
	FILE *f = fopen(FLAG, "r");
	if (!f)
		return 0;
	char c = 0;
	if (fread(&c, 1, 1, f) != 1)
		c = 0;
	fclose(f);
	return c == '1';
}

static void read_vu(void) {
	float v[8] = {0};
	FILE *f = fopen(VU, "r");
	if (f) {
		for (int i = 0; i < 8; i++) {
			if (fscanf(f, "%f", &v[i]) != 1)
				break;
		}
		fclose(f);
	}
	for (int i = 0; i < 8; i++) {
		if (v[i] > bars[i])
			bars[i] = v[i];
		else
			bars[i] *= 0.82f;
	}
}

static void box(float x0, float y0, float x1, float y1) {
	glBegin(GL_QUADS);
	glVertex2f(x0, y0);
	glVertex2f(x1, y0);
	glVertex2f(x1, y1);
	glVertex2f(x0, y1);
	glEnd();
}

static void png_path(const char *exe, char *out, size_t n) {
	const char *slash = exe ? strrchr(exe, '/') : NULL;
	if (slash)
		snprintf(out, n, "%.*s/listening.png", (int)(slash - exe), exe);
	else
		snprintf(out, n, "listening.png");
}

static GLuint load_png(const char *path, int *out_w, int *out_h) {
	int w, h, n;
	unsigned char *px = stbi_load(path, &w, &h, &n, 4);
	if (!px)
		return 0;
	GLuint tex = 0;
	glGenTextures(1, &tex);
	glBindTexture(GL_TEXTURE_2D, tex);
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, px);
	stbi_image_free(px);
	*out_w = w;
	*out_h = h;
	return tex;
}

int main(int argc, char **argv) {
	(void)argc;
	if (!glfwInit())
		return 1;
	glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 2);
	glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 1);
	glfwWindowHint(GLFW_TRANSPARENT_FRAMEBUFFER, GLFW_TRUE);
	glfwWindowHint(GLFW_DECORATED, GLFW_FALSE);
	glfwWindowHint(GLFW_FLOATING, GLFW_TRUE);
	glfwWindowHint(GLFW_FOCUS_ON_SHOW, GLFW_FALSE);
	glfwWindowHint(GLFW_RESIZABLE, GLFW_FALSE);
	int x = 0, y = 0, w = 1280, h = 800;
	GLFWmonitor *monitor = glfwGetPrimaryMonitor();
	if (monitor)
		glfwGetMonitorWorkarea(monitor, &x, &y, &w, &h);
	GLFWwindow *window = glfwCreateWindow(w, h, "DeckVoice overlay", NULL, NULL);
	if (!window)
		return 1;
	glfwSetWindowPos(window, x, y);
	Display *dpy = glfwGetX11Display();
	Window xid = glfwGetX11Window(window);
	if (dpy && xid) {
		Atom atom = XInternAtom(dpy, "GAMESCOPE_EXTERNAL_OVERLAY", False);
		uint32_t value = 1;
		XChangeProperty(dpy, xid, atom, XA_CARDINAL, 32, PropModeReplace, (unsigned char *)&value, 1);
	}
	glfwMakeContextCurrent(window);
	glfwSwapInterval(1);
	glfwGetFramebufferSize(window, &w, &h);
	char path[512];
	png_path(argv[0], path, sizeof path);
	int iw = 0, ih = 0;
	GLuint tex = load_png(path, &iw, &ih);
	while (!glfwWindowShouldClose(window)) {
		glfwPollEvents();
		glViewport(0, 0, w, h);
		glClearColor(0, 0, 0, 0);
		glClear(GL_COLOR_BUFFER_BIT);
		if (flag_on()) {
			read_vu();
			glEnable(GL_BLEND);
			glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
			glMatrixMode(GL_PROJECTION);
			glLoadIdentity();
			glOrtho(0, w, h, 0, -1, 1);
			glMatrixMode(GL_MODELVIEW);
			glLoadIdentity();
			float dh = 96;
			float dw = tex ? dh * (float)iw / (float)ih : dh;
			float bar_w = 7;
			float bar_gap = 4;
			float meter_w = 8 * bar_w + 7 * bar_gap;
			float gap = 14;
			float total = dw + gap + meter_w;
			float bx = w * 0.5f - total * 0.5f;
			float by = 28;
			if (tex) {
				glEnable(GL_TEXTURE_2D);
				glBindTexture(GL_TEXTURE_2D, tex);
				glColor4f(1, 1, 1, 0.96f);
				glBegin(GL_QUADS);
				glTexCoord2f(0, 0);
				glVertex2f(bx, by);
				glTexCoord2f(1, 0);
				glVertex2f(bx + dw, by);
				glTexCoord2f(1, 1);
				glVertex2f(bx + dw, by + dh);
				glTexCoord2f(0, 1);
				glVertex2f(bx, by + dh);
				glEnd();
				glDisable(GL_TEXTURE_2D);
			}
			float base = by + dh * 0.88f;
			float max_h = dh * 0.72f;
			float x0 = bx + dw + gap;
			for (int i = 0; i < 8; i++) {
				float bh = 5 + bars[i] * (max_h - 5);
				float x = x0 + i * (bar_w + bar_gap);
				glColor4f(0.45f, 0.95f, 0.55f, 0.45f + 0.55f * bars[i]);
				box(x, base - bh, x + bar_w, base);
			}
		}
		glfwSwapBuffers(window);
	}
	return 0;
}
