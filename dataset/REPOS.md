# Pinned Upstream Repositories

The task chains in `dataset/gold/` operate on six open-source Python projects.
Each repository is cloned at a **specific commit** listed below; the gold tests
and task scaffolds are only guaranteed to work against these exact commits.

To reproduce the environment:

```bash
mkdir -p dataset/repos && cd dataset/repos
git clone https://github.com/psf/black.git
git clone https://github.com/pallets/click.git
git clone https://github.com/httpie/httpie.git
git clone https://github.com/encode/httpx.git
git clone https://github.com/marshmallow-code/marshmallow.git
git clone https://github.com/andialbrecht/sqlparse.git

git -C black        checkout 8f4a058eeb2c664ef1cc2847d3882fc4a82fe3fa
git -C click        checkout e38188e9e205005d5af5f9e59df51904c984586a
git -C httpie       checkout 5b604c37c6c67e18e7c3e9aee6c88a8c22b98345
git -C httpx        checkout b5addb64f0161ff6bfe94c124ef76f6a1fba5254
git -C marshmallow  checkout 777ff66039fd939fc509226a33586bc3209df301
git -C sqlparse     checkout 09dbe1eec31ed1b3cd05366748865f11ba427d32
```

| Repo | Upstream URL | Pinned commit |
|---|---|---|
| black | https://github.com/psf/black | `8f4a058eeb2c664ef1cc2847d3882fc4a82fe3fa` |
| click | https://github.com/pallets/click | `e38188e9e205005d5af5f9e59df51904c984586a` |
| httpie | https://github.com/httpie/httpie | `5b604c37c6c67e18e7c3e9aee6c88a8c22b98345` |
| httpx | https://github.com/encode/httpx | `b5addb64f0161ff6bfe94c124ef76f6a1fba5254` |
| marshmallow | https://github.com/marshmallow-code/marshmallow | `777ff66039fd939fc509226a33586bc3209df301` |
| sqlparse | https://github.com/andialbrecht/sqlparse | `09dbe1eec31ed1b3cd05366748865f11ba427d32` |

Chain membership: A = black, B = click, C = httpie, D = httpx, E = marshmallow,
sqlparse = additional screening target (see `dataset/REPO_SCREENING_CN.md`).
