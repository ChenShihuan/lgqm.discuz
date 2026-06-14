# Git → 灰机 Wiki 同步配置指南

> 参考：[灰机 Wiki Git 帮助](https://www.huijiwiki.com/wiki/帮助:用Git管理MediaWiki) | [git-remote-mediawiki User Manual](https://github.com/Git-Mediawiki/Git-Mediawiki/wiki/User-manual)

## 概述

灰机 Wiki 支持通过 git 管理页面内容。底层使用 `git-remote-mediawiki` 将 MediaWiki API 映射为 git remote，实现 `git push` / `git pull` 同步 wiki 页面。

如果你需要完整使用git拉取/推送，请确保你拥有以下条件：

1. 灰机Wiki的**Bot账号**（机器人账号）
2. 向[灰机Wiki站方](https://jq.qq.com/?_wv=1027&k=aIaMXZeN)申请**X-authkey 认证头**，git推送需要此认证信息。

本文档记录本项目的配置，特别是 **X-authkey 认证头**的定制修改。

## 关键文件

| 文件               | 路径                                       | 说明                                        |
| ------------------ | ------------------------------------------ | ------------------------------------------- |
| 远程助手脚本       | `/usr/lib/git-core/git-remote-mediawiki` | git 内置，解析 `mediawiki::` 协议         |
| **定制模块** | `/usr/share/perl5/Git/Mediawiki.pm`      | **本项目修改过**，增加 X-authkey 支持 |
| 存档副本           | `doc/mediawiki-pw/Git-Mediawiki.pm`      | 上述定制模块的存档副本                      |

## 初始化 Wiki 仓库

```bash
# 从灰机 Wiki 克隆
git clone mediawiki::https://lgqm.huijiwiki.com lgqm.huijiwiki.com

# 或在已有目录中配置 remote
git init
git remote add origin mediawiki::https://lgqm.huijiwiki.com/
```

## 认证配置

编辑 `lgqm.huijiwiki.com/.git/config`：

```ini
[remote "origin"]
    url = mediawiki::https://lgqm.huijiwiki.com/
    fetch = +refs/heads/*:refs/remotes/origin/*

    # 登录凭据
    mwLogin = 紫微垣之光Bot
    mwPassword = SCUTauto2016

    # X-authkey（灰机 API 自定义认证头，必须）
    mwAuthKey = CxYUhUxSzrkG9F

    # 性能优化
    shallow = true

    # 命名空间映射
    namespacecache = File:6
    namespacecache = 文件:6
```

### X-authkey 定制修改

灰机 Wiki API 要求在 HTTP 请求头中携带 `X-authkey` 认证令牌。标准版 `Git/Mediawiki.pm` 不支持此功能。

**修改文件**：`/usr/share/perl5/Git/Mediawiki.pm`（已存档至 `doc/mediawiki-pw/Git-Mediawiki.pm`）

**改动位置**（第 66-83 行）：

```perl
# X-authkey header MUST be set before login
my $mw_auth_key = Git::config("remote.${remote_name}.mwAuthKey");
if ($mw_auth_key) {
    $wiki->{ua}->default_header('X-authkey' => $mw_auth_key);
}

if ($wiki_login) {
    my $request = {lgname => $wiki_login,
                   lgpassword => $wiki_password,
                   lgdomain => $wiki_domain};
    if ($wiki->login($request)) {
        print {*STDERR} qq(Logged in as "$wiki_login".\n);
    } else {
        print {*STDERR} qq(Login failed: ) . $wiki->{error}->{details} . "\n";
        if (!$mw_auth_key) {
            exit 1;
        }
        print {*STDERR} "Continuing with X-authkey only.\n";
    }
}
```

**改动要点**：

1. **读取 `mwAuthKey`**：从 git config 读取 `remote.origin.mwAuthKey` 的值
2. **注入 HTTP 头**：通过 `$wiki->{ua}->default_header('X-authkey' => ...)` 将所有 API 请求加上 `X-authkey` 头
3. **容错登录**：如果用户名/密码登录失败但 authkey 存在，仍继续运行（灰机 authkey 可替代登录）

> **重装系统后恢复**：将 `doc/mediawiki-pw/Git-Mediawiki.pm` 覆盖到 `/usr/share/perl5/Git/Mediawiki.pm`

## 常用操作

### 拉取 Wiki 最新内容

```bash
cd lgqm.huijiwiki.com
git rebase refs/remotes/origin/master
```

### 提交并推送

```bash
# 常规 git 工作流
echo "新内容" > 新页面.mw
git add 新页面.mw
git commit -m "导入同人: 文章名"
git push origin master
```

### 查看远程页面列表

```bash
git ls-remote origin
```

## 性能优化

| 配置项             | 说明                                              |
| ------------------ | ------------------------------------------------- |
| `shallow = true` | 只拉取每页最新版本（不拉历史），大幅减少 API 调用 |
| `namespacecache` | 缓存命名空间映射，避免重复查询                    |

## 已知限制

- **push 慢**：`git push` 会对每个变更页面逐一比对 API，页面多时很慢。替代方案：使用 `monitor/mw_push.py` 直接通过 API 推送，仅推送实际变更的文件
- **大文件超时**：单个页面过大可能 504，建议控制在 2MB 以内
- **需 WSL/Linux**：`git-remote-mediawiki` 依赖 Perl，Windows Git 不包含，需要自行安装。另外，灰机Wiki部分页面包含Windows文件系统禁止的符号，例如“ : ”等，在Windows下需要额外配置复杂的映射机制。

## 故障排查

### push 报 "Login failed"

→ 检查 `mwPassword` 和 `mwAuthKey` 是否配置正确

### push 报 "X-authkey"

→ 确认 `/usr/share/perl5/Git/Mediawiki.pm` 已替换为修改版

### fetch 极慢

→ 确认已配置 `shallow = true`

### "Namespace 'File' not known"

→ 添加 `namespacecache = File:6` 到 git config
