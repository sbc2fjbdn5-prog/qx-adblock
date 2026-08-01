# qx-adblock

Quantumult X 去广告模块专用镜像。模块及其脚本依赖均保存到本仓库，并将运行时依赖引用改写为本仓库 Raw 地址。

## 快照统计

- 去广告模块：**61 / 61**
- 已发现脚本依赖：**168**
- 成功保存脚本依赖：**168**
- 已替换为本仓库 Raw 地址的依赖引用：**291**
- 下载失败：**0**

完整列表见 [`INDEX.md`](INDEX.md)，机器可读清单见 [`manifest.json`](manifest.json)。

## 目录

- `modules/`：按来源分类的 QX 去广告模块
- `custom_sources/`：自制模块的可维护源文件
- `dependencies/`：重写文件引用的远程脚本快照
- `sources.json`：模块来源清单
- `tools/sync.py`：重新抓取并更新快照

## 更新

```bash
python3 tools/sync.py
git add modules dependencies INDEX.md manifest.json README.md sources.json
git commit -m "Update Quantumult X ad-block mirror"
git push
```

## 来源

每个文件保留原有署名和头部说明。来源仓库及上游作者拥有各自内容的相应权利；本仓库用于个人备份。
