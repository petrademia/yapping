# Vendor

Third-party code used by YAPPING.

- **ygopro-adapter** — Yu-Gi-Oh! adapter/runtime around OCGCore. Clone or maintain it here:

  ```bash
  git clone <your-adapter-repo> ygopro-adapter
  cd ygopro-adapter
  xmake f -m release -y && xmake && make
  ```

  See **docs/ENGINE_SETUP.md** for details. The run script uses `yapping/vendor/ygopro-adapter` by default.

### After pulling engine changes (rebuild native module)

YAPPING’s vendored **ygopro-adapter** may carry local patches (Lua 5.3 pin, link flags, `ygopro.h` shims). After `git pull` in `vendor/ygopro-adapter`, rebuild the extension so `import ygoenv.ygopro` keeps working:

```bash
cd vendor/ygopro-adapter
xmake f -c -m release -y
xmake b ygopro_ygoenv
# or: make build_ext
cd ../..
./.venv/bin/python -c "import ygoenv.ygopro; print('ok')"
```

Use `xmake f -c` when xmake/Lua package recipes changed (forces a clean configure).
