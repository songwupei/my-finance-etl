# 部署配置层

一份代码，多台机器。**环境差异不写进代码，写成配置数据**，这样任何一个
环境做了什么改动，`git diff` 都看得见。

## 加载顺序

后加载的覆盖先加载的：

| 顺序 | 文件 | 进 git | 放什么 |
| --- | --- | --- | --- |
| 1 | `defaults.env` | 是 | 与环境无关的默认值，所有键都在这 |
| 2 | `profiles/<主题>.env` | 是 | 该环境与默认值**不同**的键 |
| 3 | `local.env` | 否 | 本机临时覆盖、敏感值（从 `local.env.example` 复制） |

## 主题选择

`PROFILE` 默认按 `/etc/os-release` 的 `ID` 自动推导，正常不用管：

| ID | 主题 | 环境 |
| --- | --- | --- |
| `arch` | `arch` | 外网（项目在坚果云同步目录内） |
| `openEuler` | `openeuler` | 内网服务器 |

手动覆盖：

```bash
bash start.sh --profile arch
PROFILE=arch bash start.sh
```

## 已固化的差异

| 键 | arch（外网） | openeuler（内网） |
| --- | --- | --- |
| `PROJECTS_ROOT` | `/home/song/NutstoreFiles/projects` | `/home/songwp/projects` |
| `MICROMAMBA_BIN` | `/home/song/micromamba/bin/micromamba` | `/home/songwp/bin/micromamba` |
| `OPEN_BROWSER` | `true` | `false`（无桌面环境） |
| `PKG_HINT_WHIPTAIL` | `sudo pacman -S libnewt` | `sudo dnf install newt` |

两台机器相同的部分（端口 `8765/8000/5001`、环境名 `myetl`、数据区
`/home/song/NutstoreFiles/8-MyData`）只写在 `defaults.env` 里，不重复。

## 脚本约定

`start.sh` / `stop.sh` / `kill.sh` / `kill_shiny.sh` 都从 `lib.sh` 加载配置，
**端口只有一处定义**，不会再出现脚本之间端口不一致导致残留进程占住
DuckDB 锁的问题。

新增机器时：复制一个 `profiles/<主题>.env`，只写与默认值不同的行。

