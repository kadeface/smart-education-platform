# 将项目推送到 GitHub 的完整指南

## 当前状态
- **当前远程仓库：** Gitee (https://gitee.com/kadeface/score_analysis.git)
- **当前分支：** master1
- **Git 用户：** kadeface (382241106@qq.com)

## 步骤 1: 在 GitHub 上创建新仓库

1. 登录 GitHub (https://github.com)
2. 点击右上角的 "+" 号 → 选择 "New repository"
3. 填写仓库信息：
   - **Repository name:** score_analysis (或你喜欢的名字)
   - **Description:** 智能教育成绩分析系统 (可选)
   - **Visibility:** 
     - Public (公开，所有人都能看到)
     - Private (私有，只有你能看到)
   - ⚠️ **重要：不要勾选** "Add a README file"、"Add .gitignore"、"Choose a license"
     （因为我们已经有了代码）
4. 点击 "Create repository"
5. 创建成功后，GitHub 会显示仓库地址，类似：
   ```
   https://github.com/你的用户名/score_analysis.git
   ```

## 步骤 2: 更换远程仓库地址

### 方法 A: 直接替换（推荐）

```bash
# 移除旧的远程仓库
git remote remove origin

# 添加新的 GitHub 远程仓库（替换为你的真实地址）
git remote add origin https://github.com/你的用户名/仓库名.git

# 验证远程仓库设置
git remote -v
```

### 方法 B: 重命名旧仓库（保留备份）

```bash
# 将旧的远程仓库重命名为 gitee（保留备份）
git remote rename origin gitee

# 添加新的 GitHub 远程仓库
git remote add origin https://github.com/你的用户名/仓库名.git

# 验证
git remote -v
```

## 步骤 3: 推送代码到 GitHub

### 首次推送（推送所有分支和标签）

```bash
# 推送当前分支（master1）并设置上游分支
git push -u origin master1

# 如果需要推送所有分支
git push -u origin --all

# 如果需要推送所有标签
git push -u origin --tags
```

### 推送其他分支（如果需要）

```bash
# 推送 master 分支
git checkout master
git push -u origin master

# 推送 master1-layer 分支
git checkout master1-layer
git push -u origin master1-layer
```

## 步骤 4: 处理认证（如果遇到问题）

### 如果使用 HTTPS（需要 Personal Access Token）

1. GitHub 设置 → Developer settings → Personal access tokens → Tokens (classic)
2. 生成新 token，权限至少勾选：`repo`
3. 推送时使用 token 作为密码

### 如果使用 SSH（推荐，更安全）

1. 检查是否已有 SSH 密钥：
   ```bash
   ls -al ~/.ssh
   ```

2. 如果没有，生成新密钥：
   ```bash
   ssh-keygen -t ed25519 -C "382241106@qq.com"
   ```

3. 添加 SSH 密钥到 GitHub：
   - 复制公钥内容：`cat ~/.ssh/id_ed25519.pub`
   - GitHub 设置 → SSH and GPG keys → New SSH key
   - 粘贴公钥并保存

4. 更换远程地址为 SSH 格式：
   ```bash
   git remote set-url origin git@github.com:你的用户名/仓库名.git
   ```

## 注意事项

1. ⚠️ **提交当前更改前先提交**：
   - 当前有已暂存的文件（.gitignore, requirements.txt, settings.py）
   - 建议先提交这些更改，然后再推送

2. ⚠️ **敏感信息检查**：
   - 检查 `settings.py` 中是否有敏感信息（如 SECRET_KEY）
   - 考虑使用环境变量

3. ⚠️ **大文件处理**：
   - 如果仓库中有大文件，可能需要使用 Git LFS

## 快速命令参考

```bash
# 查看当前远程仓库
git remote -v

# 查看所有分支
git branch -a

# 查看当前状态
git status

# 查看提交历史
git log --oneline -10
```

## 完成后验证

推送成功后，访问你的 GitHub 仓库页面，应该能看到：
- 所有代码文件
- 提交历史
- 分支信息

