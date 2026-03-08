# Vendor

Third-party code used by YAPPING.

- **ygo-env** — Yu-Gi-Oh! engine (izzak98/ygo-env). Clone and build here so you can modify it if needed:

  ```bash
  git clone https://github.com/izzak98/ygo-env.git ygo-env
  cd ygo-env
  xmake f -m release -y && xmake && make
  ```

  See **docs/ENGINE_SETUP.md** for details. The run script uses `yapping/vendor/ygo-env` by default.
