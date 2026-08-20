import commonjs from '@rollup/plugin-commonjs';
import json from '@rollup/plugin-json';
import { nodeResolve } from '@rollup/plugin-node-resolve';
import replace from '@rollup/plugin-replace';
import typescript from '@rollup/plugin-typescript';
import importAssets from 'rollup-plugin-import-assets';
import { defineConfig } from 'rollup';
import { readFileSync } from 'fs';

const pluginManifest = JSON.parse(readFileSync('./plugin.json', 'utf8'));

const deckyManifest = {
  name: 'decky-manifest',
  resolveId(id) {
    return id === '@decky/manifest' ? '\0decky-manifest' : null;
  },
  load(id) {
    return id === '\0decky-manifest'
      ? `export default ${JSON.stringify(pluginManifest)};`
      : null;
  },
};

export default defineConfig({
  input: './src/index.tsx',
  plugins: [
    deckyManifest,
    commonjs(),
    nodeResolve(),
    typescript(),
    json(),
    replace({
      preventAssignment: false,
      'process.env.NODE_ENV': JSON.stringify('production'),
    }),
    importAssets({
      publicPath: `http://127.0.0.1:1337/plugins/DeckVoice/`,
    }),
  ],
  context: 'window',
  external: ['react', 'react-dom', 'decky-frontend-lib'],
  output: {
    file: 'dist/index.js',
    globals: {
      react: 'SP_REACT',
      'react-dom': 'SP_REACTDOM',
      'decky-frontend-lib': 'DFL',
    },
    format: 'iife',
    exports: 'default',
  },
});
