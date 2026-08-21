#define GLFW_EXPOSE_NATIVE_X11
#include <GL/gl.h>
#include <GLFW/glfw3.h>
#include <GLFW/glfw3native.h>
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
#define STB_TRUETYPE_IMPLEMENTATION
#include "stb_truetype.h"

static const char *FLAG = "/tmp/deckvoice_ptt";
static const char *VU = "/tmp/deckvoice_vu";
static const char *PENDING = "/tmp/deckvoice_pending";
static float bars[8];
static stbtt_fontinfo font;
static int font_ok;
static GLuint text_tex;
static int text_tw, text_th;
static char pending[512];
static char pending_drawn[512];

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

static void read_pending(void) {
	pending[0] = 0;
	FILE *f = fopen(PENDING, "r");
	if (!f)
		return;
	size_t n = fread(pending, 1, sizeof pending - 1, f);
	fclose(f);
	pending[n] = 0;
	while (n && (pending[n - 1] == '\n' || pending[n - 1] == '\r'))
		pending[--n] = 0;
}

static unsigned utf8_next(const char **s) {
	const unsigned char *p = (const unsigned char *)*s;
	if (!p[0])
		return 0;
	if (p[0] < 0x80) {
		*s += 1;
		return p[0];
	}
	if ((p[0] & 0xe0) == 0xc0 && p[1]) {
		unsigned c = ((p[0] & 0x1f) << 6) | (p[1] & 0x3f);
		*s += 2;
		return c;
	}
	if ((p[0] & 0xf0) == 0xe0 && p[1] && p[2]) {
		unsigned c = ((p[0] & 0x0f) << 12) | ((p[1] & 0x3f) << 6) | (p[2] & 0x3f);
		*s += 3;
		return c;
	}
	if ((p[0] & 0xf8) == 0xf0 && p[1] && p[2] && p[3]) {
		unsigned c = ((p[0] & 0x07) << 18) | ((p[1] & 0x3f) << 12) | ((p[2] & 0x3f) << 6) | (p[3] & 0x3f);
		*s += 4;
		return c;
	}
	*s += 1;
	return 0xfffd;
}

static int load_font(void) {
	static const char *paths[] = {
		"/usr/share/fonts/TTF/DejaVuSans.ttf",
		"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
		"/usr/share/fonts/noto/NotoSans-Regular.ttf",
		"/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
		NULL,
	};
	for (int i = 0; paths[i]; i++) {
		FILE *f = fopen(paths[i], "rb");
		if (!f)
			continue;
		fseek(f, 0, SEEK_END);
		long n = ftell(f);
		fseek(f, 0, SEEK_SET);
		if (n <= 0) {
			fclose(f);
			continue;
		}
		unsigned char *data = malloc((size_t)n);
		if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) {
			free(data);
			fclose(f);
			continue;
		}
		fclose(f);
		if (stbtt_InitFont(&font, data, 0)) {
			font_ok = 1;
			return 1;
		}
		free(data);
	}
	return 0;
}

static void render_pending(void) {
	if (!font_ok || !pending[0] || strcmp(pending, pending_drawn) == 0)
		return;
	snprintf(pending_drawn, sizeof pending_drawn, "%s", pending);
	float px = 26.0f;
	float scale = stbtt_ScaleForPixelHeight(&font, px);
	int ascent, descent, line_gap;
	stbtt_GetFontVMetrics(&font, &ascent, &descent, &line_gap);
	float lh = (ascent - descent + line_gap) * scale;
	const char *s = pending;
	int lines = 1;
	int max_w = 0;
	int x = 0;
	while (*s) {
		if (*s == '\n') {
			if (x > max_w)
				max_w = x;
			x = 0;
			lines++;
			s++;
			continue;
		}
		unsigned cp = utf8_next(&s);
		int adv, lsb;
		stbtt_GetCodepointHMetrics(&font, (int)cp, &adv, &lsb);
		x += (int)(adv * scale);
	}
	if (x > max_w)
		max_w = x;
	int tw = max_w + 8;
	int th = (int)(lh * lines) + 8;
	if (tw < 8)
		tw = 8;
	if (th < 8)
		th = 8;
	unsigned char *bmp = calloc((size_t)tw * th, 1);
	if (!bmp)
		return;
	s = pending;
	float ypos = 4 + ascent * scale;
	float xpos = 4;
	while (*s) {
		if (*s == '\n') {
			xpos = 4;
			ypos += lh;
			s++;
			continue;
		}
		unsigned cp = utf8_next(&s);
		int adv, lsb, x0, y0, x1, y1;
		stbtt_GetCodepointHMetrics(&font, (int)cp, &adv, &lsb);
		stbtt_GetCodepointBitmapBox(&font, (int)cp, scale, scale, &x0, &y0, &x1, &y1);
		int gx = (int)xpos + x0;
		int gy = (int)ypos + y0;
		int gw = x1 - x0;
		int gh = y1 - y0;
		if (gx >= 0 && gy >= 0 && gx + gw <= tw && gy + gh <= th)
			stbtt_MakeCodepointBitmap(&font, bmp + gy * tw + gx, gw, gh, tw, scale, scale, (int)cp);
		xpos += adv * scale;
	}
	unsigned char *rgba = malloc((size_t)tw * th * 4);
	if (!rgba) {
		free(bmp);
		return;
	}
	for (int i = 0; i < tw * th; i++) {
		rgba[i * 4] = 255;
		rgba[i * 4 + 1] = 255;
		rgba[i * 4 + 2] = 255;
		rgba[i * 4 + 3] = bmp[i];
	}
	free(bmp);
	if (!text_tex)
		glGenTextures(1, &text_tex);
	glBindTexture(GL_TEXTURE_2D, text_tex);
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tw, th, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
	free(rgba);
	text_tw = tw;
	text_th = th;
}

static void box(float x0, float y0, float x1, float y1) {
	glBegin(GL_QUADS);
	glVertex2f(x0, y0);
	glVertex2f(x1, y0);
	glVertex2f(x1, y1);
	glVertex2f(x0, y1);
	glEnd();
}

static void tex_rect(float x, float y, float w, float h) {
	glBegin(GL_QUADS);
	glTexCoord2f(0, 0);
	glVertex2f(x, y);
	glTexCoord2f(1, 0);
	glVertex2f(x + w, y);
	glTexCoord2f(1, 1);
	glVertex2f(x + w, y + h);
	glTexCoord2f(0, 1);
	glVertex2f(x, y + h);
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

static void begin_hud(int w, int h) {
	glEnable(GL_BLEND);
	glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
	glMatrixMode(GL_PROJECTION);
	glLoadIdentity();
	glOrtho(0, w, h, 0, -1, 1);
	glMatrixMode(GL_MODELVIEW);
	glLoadIdentity();
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
	load_font();
	while (!glfwWindowShouldClose(window)) {
		glfwPollEvents();
		glViewport(0, 0, w, h);
		glClearColor(0, 0, 0, 0);
		glClear(GL_COLOR_BUFFER_BIT);
		int ptt = flag_on();
		read_pending();
		if (ptt || pending[0]) {
			begin_hud(w, h);
			if (ptt) {
				read_vu();
				float dh = 48;
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
					float o = 2;
					glColor4f(0, 0, 0, 0.96f);
					for (int dy = -1; dy <= 1; dy++)
						for (int dx = -1; dx <= 1; dx++)
							if (dx || dy)
								tex_rect(bx + dx * o, by + dy * o, dw, dh);
					glColor4f(1, 1, 1, 0.96f);
					tex_rect(bx, by, dw, dh);
					glDisable(GL_TEXTURE_2D);
				}
				float cy = by + dh * 0.5f;
				float max_half = dh * 0.4f;
				float x0 = bx + dw + gap;
				for (int i = 0; i < 8; i++) {
					float half = 2.5f + bars[i] * (max_half - 2.5f);
					float x = x0 + i * (bar_w + bar_gap);
					glColor4f(0.0f, 0.52f, 0.22f, 0.92f + 0.08f * bars[i]);
					box(x, cy - half, x + bar_w, cy + half);
				}
			} else {
				render_pending();
				if (text_tex && pending[0]) {
					float tw = (float)text_tw;
					float th = (float)text_th;
					float tx = w * 0.5f - tw * 0.5f;
					float ty = 28;
					float pad = 10;
					glColor4f(0, 0, 0, 0.72f);
					box(tx - pad, ty - pad, tx + tw + pad, ty + th + pad);
					glEnable(GL_TEXTURE_2D);
					glBindTexture(GL_TEXTURE_2D, text_tex);
					float o = 2;
					glColor4f(0, 0, 0, 0.96f);
					for (int dy = -1; dy <= 1; dy++)
						for (int dx = -1; dx <= 1; dx++)
							if (dx || dy)
								tex_rect(tx + dx * o, ty + dy * o, tw, th);
					glColor4f(1, 1, 1, 0.96f);
					tex_rect(tx, ty, tw, th);
					glDisable(GL_TEXTURE_2D);
				}
			}
		}
		glfwSwapBuffers(window);
	}
	return 0;
}
