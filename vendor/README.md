# Vendor

Third-party code used by YAPPING.

- **yapcore** — Yu-Gi-Oh! adapter/runtime around OCGCore. Clone or maintain it here:

  ```bash
  git clone <your-adapter-repo> yapcore
  cd yapcore
  xmake f -m release -y && xmake && make
  ```

  See **docs/ENGINE_SETUP.md** for details. The run script uses `yapping/vendor/yapcore` by default.

### After pulling engine changes (rebuild native module)

YAPPING’s vendored **yapcore** may carry local patches (Lua 5.3 pin, link flags, `ygopro.h` shims). After `git pull` in `vendor/yapcore`, rebuild the extension so `import ygoenv.ygopro` keeps working:

```bash
cd vendor/yapcore
xmake f -c -m release -y
xmake b ygopro_ygoenv
# or: make build_ext
cd ../..
./.venv/bin/python -c "import ygoenv.ygopro; print('ok')"
```

Use `xmake f -c` when xmake/Lua package recipes changed (forces a clean configure).
