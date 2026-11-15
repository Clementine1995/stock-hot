# WORKFLOW.md

## 职责

本文件是初始化、构建、启动、验证、Git、数据库、环境晋级、发布和发布后检查的**唯一可执行命令来源**。授权边界见 `AGENTS.md`，协作与证据见 `COLLABORATION.md`，架构红线见 `ARCHITECTURE.md`。

`{{...}}` 是不可执行占位符，实例化前禁止复制运行任何未完全替换的命令块。每个命令块写明工作目录、目标环境、前置条件、状态影响和成功判定。

## 环境身份门禁

每个允许修改、运行、真实联调或发布的环境或资源边界必须提供「实际身份校验」，不能只检查分支名或配置文件存在。校验至少覆盖：当前工作区 / 提交 / 制品摘要、实际加载的配置来源、数据库或存储边界、外部接口边界、危险功能开关；输出只含非敏感摘要。

```text
{{environment_identity_gate_commands}}
```

通过标准：`{{environment_identity_gate_success}}`

## 初始化与构建

```text
{{prerequisite_check_commands}}
{{dependency_install_commands}}
{{build_commands}}
```

安装依赖会影响本地依赖目录或锁文件，未经授权不得执行安装、升级或移除。

## 本地运行与启动

```text
{{local_run_invoke_or_start_commands}}
{{local_stop_or_restart_commands}}
{{local_smoke_selfcheck_or_health_commands}}
```

必须明确状态 / 健康 / 自检入口是只读观测，还是会启动、重启或修复进程；具备操作副作用的入口不得伪装成健康检查。

## 自动化验证

```text
{{targeted_test_commands}}
{{related_regression_commands}}
{{full_test_commands}}
{{static_type_format_check_commands}}
git diff --check
```

自动化测试不得连接、创建、启动、重启或清空真实数据库与外部系统；对应 client 使用替身或进程内实现。每个实施单元选择与风险匹配的验证层级。

## Git 与版本控制基线

- 未经明确授权，不执行 `git add`、`git commit`、`git push`、`git pull`。
- 不 rewrite 共享历史、不强推；历史集成与恢复策略：`{{git_history_integration_and_recovery_policy}}`。
- 只暂存当前任务文件，保留任务开始前已有的未提交修改。

### 开发前只读检查

```text
git status --short --branch
git rev-parse --abbrev-ref HEAD
git diff --name-only
```

确认：工作区与代码线正确、无未完成合并、用户已有修改已识别且不会被覆盖或混入、本任务修改范围与已有修改不重叠。

### 提交前检查

```text
git status --short --branch
{{targeted_or_full_validation_commands}}
git diff --check
git diff
```

### 提交与推送（需分别授权）

```text
git add {{current_task_files_only}}
git commit -m "{{commit_message}}"
git push {{remote_name}} {{source_branch}}
```

## 数据库结构与数据变更

唯一入口：`{{schema_change_entry}}`；禁止入口：`{{forbidden_schema_change_entries}}`。

结构变更固定顺序：形成唯一最终 Schema / DDL / 迁移并同步代码模型与结构测试 → 说明环境、库名、目标对象、锁表风险与完整命令并取得逐次授权 → 执行 `{{schema_preflight_commands}}` → 执行 `{{schema_apply_commands}}` → 用 `{{schema_readback_commands}}` 只读回查 → 不一致时停止后续发布。

数据修复或回填固定顺序：只读确认范围与行数 → 提供幂等性、批量边界、停止条件与回查 SQL 并取得单独授权 → 执行 → 只读验收 → 保存证据。不允许在未知现场直接运行通用回滚脚本。

## CI/CD 与自动化执行

没有 CI/CD 时删除本节。CI 配置入口：`{{ci_configuration_entry}}`；触发条件：`{{ci_triggers}}`；必需检查与分支保护：`{{ci_required_checks_and_branch_protection}}`；发布授权模型：`{{release_authorization_model}}`。CI 必须调用与本地等价的稳定入口，不在流水线中复制另一套隐式构建或测试逻辑。

## 发布身份模型

没有多环境发布的项目可删除本节。使用以下通用身份，实例化时映射为 Git SHA、镜像 digest、包校验和或发布系统的不可变 ID：

- `validated_source_identity`：通过发布前完整验证的源代码或制品身份。
- `tested_source_identity`：在前置验证环境完成业务验收的同一身份。
- `target_release_identity`：目标环境实际部署的代码或制品身份。

硬规则：`tested_source_identity` 必须来源于 `validated_source_identity`，且二者一致或具备可验证的不可变映射；最终环境发布前，当前源身份必须仍等于 `tested_source_identity`；源代码、依赖、构建参数或制品变化会产生新身份，原验收失效。

## 发布前源基线门禁

```text
{{pre_release_source_sync_commands}}
{{source_environment_identity_gate_commands}}
{{release_validation_commands}}
{{emit_validated_source_identity_commands}}
```

通过标准：工作区干净且身份明确、本地源与权威远端一致、验证按风险通过、输出完整 `validated_source_identity`。门禁导致源变化时停止发布，修正后从头执行。

## 发布后检查

```text
{{post_release_identity_check_commands}}
{{post_release_health_check_commands}}
{{post_release_log_check_commands}}
```

必须验证适用项：目标环境实际代码 / 制品身份、实际配置身份、平台 / 工作负载状态、smoke / 健康检查、关键日志无新增阻塞问题。发布后默认只读检查，写链路与后台任务另行授权。

## 超时、中断与未知现场

迁移、远端命令或真实联调超时、断连或结果不明时：停止重复执行；记录最后一个已确认成功的步骤；用 `{{unknown_state_readonly_inspection_commands}}` 只读核对锁、track、临时资源、当前代码 / 制品身份、平台状态与日志；区分「未执行 / 执行中断 / 已生效但响应丢失 / 失败后部分生效」；根据现场提出继续、补验或人工恢复方案，未经确认不删除现场、不回滚、不盲目重跑。

## 后台任务和真实写入口

项目没有后台任务或真实写入口时删除本节。

```text
{{background_job_or_real_write_commands}}
```

以上命令会造成 `{{background_job_or_write_impact}}`。每次执行前必须说明环境、业务范围、重复运行语义、预计写入量、停止条件和回查方式，并取得单独授权。

## 交付节奏

- 开发 → 更新说明 → 验证（类型检查 / 测试 / 构建 / 冒烟）→ 清理提交；先执行后总结验证。
- 涉及配置、迁移、升级的改动，同步更新对应文档与升级说明。
- 多机开发时：明确开发机与任务机的职责分工，跨机提交前校验提交链路一致性。
