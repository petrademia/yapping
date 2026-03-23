# Vendor

Third-party code used by YAPPING.

- **ygo-env** — Yu-Gi-Oh! engine. For YAPPING use **[petrademia/ygo-env](https://github.com/petrademia/ygo-env)**. Clone and build here:

  ```bash
  git clone https://github.com/petrademia/ygo-env.git ygo-env
  cd ygo-env
  xmake f -m release -y && xmake && make
  ```

  See **docs/ENGINE_SETUP.md** for details. The run script uses `yapping/vendor/ygo-env` by default.

### After pulling engine changes (rebuild native module)

YAPPING’s vendored **ygo-env** may carry local patches (Lua 5.3 pin, link flags, `ygopro.h` shims). After `git pull` in `vendor/ygo-env`, rebuild the extension so `import ygoenv.ygopro` keeps working:

```bash
cd vendor/ygo-env
xmake f -c -m release -y
xmake b ygopro_ygoenv
# or: make build_ext
cd ../..
./.venv/bin/python -c "import ygoenv.ygopro; print('ok')"
```

Use `xmake f -c` when xmake/Lua package recipes changed (forces a clean configure).
