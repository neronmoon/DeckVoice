#!/bin/sh
set -eu

cd /backend
mkdir -p out/python out/lib out/licenses
cp -R /runtime/python/. out/python/

find out/python -type d \( -name __pycache__ -o -name tests -o -name test \) \
    -prune -exec rm -rf '{}' +
find out/python -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

if find out/python -type f -name '*cpython-313*' | grep -q .; then
    echo "error: Python 3.13 extension found in the Decky Python 3.11 bundle" >&2
    exit 1
fi
if ! find out/python -type f -name '*cpython-311*' | grep -q .; then
    echo "error: no Python 3.11 extension modules found in runtime bundle" >&2
    exit 1
fi

cp /ydotool-build/ydotool /ydotool-build/ydotoold out/
cp /whisper-build/whisper-server out/
cp -a /whisper-build/lib/. out/lib/
cp -L /usr/lib/libportaudio.so.2 out/lib/libportaudio.so.2
cp /ydotool-src/LICENSE out/licenses/ydotool-AGPL-3.0.txt
cp /usr/share/licenses/portaudio/LICENSE.txt out/licenses/portaudio-MIT.txt
cp /whisper-build/LICENSE out/licenses/whisper.cpp-MIT.txt
