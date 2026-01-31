# Git 多设备同步学习仓库指南

> 适用场景：克隆开源项目学习，需要在多台电脑（如 Mac + Windows）间同步自己的学习笔记和修改。

## 目录

- [核心概念](#核心概念)
- [初次设置（主电脑）](#初次设置主电脑)
- [其他设备克隆](#其他设备克隆)
- [日常同步操作](#日常同步操作)
- [常见问题](#常见问题)

---

## 核心概念

### 为什么需要 Fork？

直接克隆的开源仓库，你没有写权限，无法推送自己的修改。Fork 到自己账号后：

```
origin          → 原作者仓库（只读，获取上游更新）
mine/origin     → 你的 Fork（读写，保存你的修改）
```

### Fork 后会与原仓库失联吗？

**不会。** Git 支持多个 remote，你可以同时：
- 从原仓库拉取最新更新
- 向自己的仓库推送修改

---

## 初次设置（主电脑）

### 步骤 1：Fork 原仓库

1. 打开原仓库 GitHub 页面
2. 点击右上角 **Fork** 按钮
3. 选择你的账号，完成 Fork

### 步骤 2：添加你的仓库为 remote

```bash
# 查看当前 remote（应该只有 origin 指向原仓库）
git remote -v

# 添加你的 Fork 为新的 remote（二选一）
# 方式一：命名为 mine（推荐，语义清晰）
git remote add mine https://github.com/你的用户名/仓库名.git

# 方式二：重命名 origin，把你的仓库设为 origin
git remote rename origin upstream
git remote add origin https://github.com/你的用户名/仓库名.git
```

### 步骤 3：创建学习分支

```bash
# 创建并切换到学习分支（保持 main 干净，方便同步上游）
git checkout -b learning/my-study

# 或者用你喜欢的分支名
git checkout -b study
git checkout -b notes
```

### 步骤 4：提交并推送

```bash
# 添加所有修改
git add -A

# 提交
git commit -m "学习笔记：xxx模块分析"

# 首次推送，设置上游跟踪
git push -u mine learning/my-study
```

---

## 其他设备克隆

### Windows / 其他电脑

```bash
# 1. 克隆你的 Fork（不是原仓库！）
git clone https://github.com/你的用户名/仓库名.git

# 2. 进入目录
cd 仓库名

# 3. 切换到学习分支
git checkout learning/my-study

# 4. 添加原仓库为 remote（用于获取上游更新）
git remote add upstream https://github.com/原作者/仓库名.git

# 5. 验证 remote 配置
git remote -v
# 应该显示：
# origin    https://github.com/你的用户名/仓库名.git (fetch)
# origin    https://github.com/你的用户名/仓库名.git (push)
# upstream  https://github.com/原作者/仓库名.git (fetch)
# upstream  https://github.com/原作者/仓库名.git (push)
```

---

## 日常同步操作

### 多设备间同步（最常用）

```bash
# 拉取最新修改（在开始工作前）
git pull

# 推送本地修改（完成工作后）
git add -A
git commit -m "更新笔记"
git push
```

### 同步原仓库更新

当原作者更新了代码，你想获取最新内容：

```bash
# 方式一：在学习分支直接合并
git fetch upstream          # 获取上游更新
git merge upstream/main     # 合并到当前分支

# 方式二：先更新 main，再合并到学习分支（更规范）
git checkout main           # 切到 main
git pull upstream main      # 拉取上游最新
git checkout learning/my-study  # 切回学习分支
git merge main              # 合并 main 的更新

# 推送合并后的结果
git push
```

### 处理冲突

如果你修改的文件与上游更新冲突：

```bash
# 合并时会提示冲突文件
git merge upstream/main
# CONFLICT (content): Merge conflict in xxx.py

# 1. 打开冲突文件，手动解决（保留你需要的部分）
# 2. 标记为已解决
git add xxx.py

# 3. 完成合并
git commit -m "合并上游更新，解决冲突"

# 4. 推送
git push
```

---

## 常见问题

### Q1: 我应该用 `mine` 还是 `origin` 作为我的仓库名？

**两种方式都可以：**

| 方式 | origin 指向 | 优点 | 缺点 |
|------|-------------|------|------|
| 保留 origin | 原作者仓库 | 不改变默认配置 | push 需要指定 `mine` |
| 重命名 | 你的 Fork | `git push` 更简单 | 需要记住 `upstream` |

**推荐：** 如果经常推送，建议把你的 Fork 设为 `origin`。

### Q2: 为什么要单独建学习分支？

1. **保持 main 干净** - 方便与上游同步
2. **隔离你的修改** - 不会和原代码混在一起
3. **便于对比** - 随时可以 `git diff main` 看你改了什么

### Q3: 多台电脑修改了同一个文件怎么办？

```bash
# 先拉取远程最新
git pull

# 如果有冲突，解决后提交
git add -A
git commit -m "解决冲突"
git push
```

### Q4: 我想放弃本地修改，完全同步远程

```bash
# 放弃本地所有未提交的修改
git checkout .
git clean -fd

# 强制同步远程（谨慎使用！）
git fetch origin
git reset --hard origin/learning/my-study
```

### Q5: 查看当前状态的常用命令

```bash
git status          # 查看修改状态
git branch -a       # 查看所有分支
git remote -v       # 查看所有 remote
git log --oneline -5  # 查看最近5次提交
```

---

## 快速参考卡片

```
┌─────────────────────────────────────────────────────────┐
│  Git 多设备同步 - 快速参考                               │
├─────────────────────────────────────────────────────────┤
│  日常工作流：                                            │
│    开始前:  git pull                                     │
│    完成后:  git add -A && git commit -m "msg" && git push│
├─────────────────────────────────────────────────────────┤
│  同步上游:                                               │
│    git fetch upstream                                    │
│    git merge upstream/main                               │
│    git push                                              │
├─────────────────────────────────────────────────────────┤
│  Remote 约定:                                            │
│    origin/mine  = 你的 Fork（可读写）                    │
│    upstream     = 原作者仓库（只读）                      │
└─────────────────────────────────────────────────────────┘
```

---

## 实际案例

以 `agent-service-toolkit` 为例：

```bash
# 主电脑配置
git remote -v
# mine    https://github.com/hengwujun128/agent-service-toolkit.git
# origin  https://github.com/JoshuaC215/agent-service-toolkit.git

# 学习分支
git branch
# * learning/my-study
#   main
```

Windows 电脑克隆后的配置：

```bash
git remote -v
# origin    https://github.com/hengwujun128/agent-service-toolkit.git
# upstream  https://github.com/JoshuaC215/agent-service-toolkit.git
```
