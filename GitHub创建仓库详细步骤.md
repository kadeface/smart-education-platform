# 如何在 GitHub 上创建新仓库 - 详细步骤

## 前置准备

1. **确保已有 GitHub 账号**
   - 如果没有，访问 https://github.com 注册
   - 使用邮箱注册（建议使用：382241106@qq.com）

2. **登录 GitHub 账号**

---

## 创建仓库步骤

### 步骤 1: 进入创建页面

1. 打开浏览器，访问 https://github.com
2. 点击右上角的 **"+"** 号（加号图标）
3. 在下拉菜单中选择 **"New repository"**（新建仓库）

   ```
   界面示意：
   ┌─────────────────┐
   │  GitHub Logo    │              [+]  ← 点击这里
   └─────────────────┘
   ```

### 步骤 2: 填写仓库信息

你会看到创建仓库的表单，需要填写以下信息：

#### 2.1 Repository name（仓库名称）
- **推荐名称：** `score_analysis` 或 `intelligent-education-score-analysis`
- **规则：**
  - 只能包含字母、数字、连字符(-)和下划线(_)
  - 不能包含空格
  - 建议使用小写字母

#### 2.2 Description（描述，可选）
- 例如：`智能教育成绩分析系统 - 基于Django和人工智能的教育数据平台`
- 也可以留空

#### 2.3 Visibility（可见性）
选择仓库的可见性：

- **Public（公开）**
  - ✅ 任何人都可以查看你的代码
  - ✅ 适合开源项目
  - ✅ 免费的私有仓库数量有限制

- **Private（私有）**
  - 🔒 只有你（和你授权的人）可以查看
  - 🔒 需要付费（或使用 GitHub Education Pack）
  - 🔒 适合个人项目或商业项目

**建议：** 如果代码不涉及敏感信息，选择 **Public**；否则选择 **Private**

#### 2.4 初始化选项 ⚠️ 重要

在创建仓库页面底部，有三个选项，**全部不要勾选**：

```
☐ Add a README file
☐ Add .gitignore
☐ Choose a license
```

**为什么不要勾选？**
- 我们已经有了代码和文件
- 勾选会创建一个新的初始提交
- 推送时会与本地历史冲突

### 步骤 3: 创建仓库

1. 确认所有信息填写正确
2. 点击绿色的 **"Create repository"** 按钮

---

## 步骤 4: 获取仓库地址

创建成功后，GitHub 会自动跳转到仓库页面。你会看到类似这样的页面：

### 如果仓库是空的（推荐的情况）

页面会显示：

```
Quick setup — if you've done this kind of thing before
https://github.com/你的用户名/score_analysis.git

…or create a new repository on the command line
…or push an existing repository from the command line
```

**复制 HTTPS 地址**（格式如下）：
```
https://github.com/你的用户名/仓库名.git
```

例如：
```
https://github.com/kadeface/score_analysis.git
```

### 如果你不小心勾选了初始化选项

页面会显示 README 文件。这种情况下，你需要：
1. 先删除 README.md 文件（或后续处理合并冲突）
2. 或者按照下面的"合并策略"处理

---

## 重要提示

### ✅ 创建前检查清单

- [ ] GitHub 账号已登录
- [ ] 仓库名称已确定（建议：`score_analysis`）
- [ ] 可见性已选择（Public 或 Private）
- [ ] **三个初始化选项都未勾选** ⚠️
- [ ] 已经准备好仓库地址用于后续操作

### 📋 你需要记录的信息

创建成功后，请记录：
1. **仓库完整地址：** `https://github.com/你的用户名/仓库名.git`
2. **仓库名称：** 例如 `score_analysis`
3. **你的 GitHub 用户名：** 例如 `kadeface`

---

## 创建后的下一步

仓库创建完成后，请告诉我：
- 你的 GitHub 用户名
- 仓库名称
- 完整的仓库地址

我会帮你：
1. 更换本地 Git 的远程仓库地址
2. 推送代码到 GitHub
3. 配置分支追踪关系

---

## 常见问题

### Q: 如何知道我的 GitHub 用户名？
A: 登录后，点击右上角头像，用户名显示在头像下方，或者查看浏览器地址栏，通常在：
`https://github.com/你的用户名`

### Q: 仓库名称可以包含中文吗？
A: 不建议。虽然可以，但可能在某些工具中显示异常。建议使用英文。

### Q: 创建时不小心勾选了初始化选项怎么办？
A: 有几种处理方式：
1. 删除仓库重新创建（最简单）
2. 或者后续推送时处理合并冲突
3. 或者先拉取再强制推送（不推荐，会丢失远程的提交）

### Q: Private 仓库要收费吗？
A: GitHub 现在提供免费的私有仓库（有数量限制），对于个人使用通常足够。

### Q: 忘记复制仓库地址怎么办？
A: 在仓库页面，点击绿色的 **"Code"** 按钮，会显示仓库地址（HTTPS 或 SSH）。

---

## 创建仓库的命令行方式（高级，可选）

如果你更喜欢命令行，也可以使用 GitHub CLI：

```bash
# 安装 GitHub CLI (gh)
# Windows: choco install gh
# 或下载安装包: https://cli.github.com/

# 登录
gh auth login

# 创建仓库
gh repo create score_analysis --public --source=. --remote=origin --push
```

但对于新手，建议使用网页方式创建。

