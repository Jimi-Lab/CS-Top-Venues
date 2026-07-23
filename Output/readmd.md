## 候选池主要针对AI for Sec、AI Safety、AI for SE。



### AI for Sec大类（包括但不限于以下方向）：
LLM/Agent for Vulnerability Discovery、代码审计、根因与攻击路径
AI for Vulnerability Lifecycle：提交、补丁、版本、backport
AI for Automated Program Repair / Security Patch
AI for Fuzzing / Program Analysis
Autonomous Cybersecurity Agents
AI for Software Supply Chain Security
AI for Exploitability and Attack-Path Reasoning
AI for Security Patch Validation
AI + Formal Methods for Security
AI for Binary Lifting / Decompilation / Compiler-Aware Analysis
Security Agent Evaluation and Benchmarks
AI 辅助 Web/API/Cloud/IaC 配置安全与漏洞发现
AI for malware analysis、恶意代码家族分析、行为检测与溯源
AI 辅助渗透测试、自动化 reconnaissance、攻击链生成与红队
Vulnerability Intelligence：CVE/CWE/CAPEC、漏洞报告、PoC、威胁情报关联
AI for mobile/IoT/embedded/firmware security
AI for vulnerability prioritization、风险评估、修复优先级与 exploit prediction
AI for security configuration、权限误配、身份与访问控制分析
AI for code provenance、第三方依赖识别、恶意包与软件供应链投毒
AI for runtime detection/response：告警关联、入侵检测、取证与自动响应
AI for security testing：test generation、differential testing、sanitizer-guided testing



### AI Safety大类（包括但不限于以下方向）：
Agentic AI Security、MCP、RAG、tool/memory/multi-agent 安全
可验证、可审计的安全智能体
Secure Coding Agents / Coding-Agent Assurance
Multimodal / CUA Security
AI Data, Privacy, and Knowledge Security
AI system red teaming 与自动化安全测试
Agent 身份、认证、授权、最小权限与审计追踪
Agent-to-Agent / 多 Agent 协议、委托链与信任传播安全
AI 模型与 Agent 供应链安全：模型权重、LoRA、插件、工具、提示词模板、MCP server
模型窃取、成员推断、模型反演、训练数据提取与输出泄露
模型后门、数据投毒、知识库投毒与检索操纵
AI serving/inference security：跨租户隔离、缓存泄露、侧信道、模型 API 滥用
AI 安全治理：可追责性、策略执行、运行时监控、风险度量
Agent world model / environment feedback 欺骗与长期记忆投毒
AI coding assistant 安全：不安全代码生成、依赖投毒、代码执行与工具调用越权



### AI For SE大类（包括但不限于以下方向）:
Binary/Firmware + AI + 编译优化语义恢复
Security-oriented AI for SE：repository reasoning、Git history、coding agent
安全需求到代码/配置的追踪与验证
Issue/CVE/report-to-code、report-to-patch、commit-to-CVE 推理
安全回归测试、补丁测试与修复传播验证
安全代码迁移、API/依赖升级、backport 与跨分支修复迁移
DevSecOps / CI-CD Agent、代码审查 Agent、release security
软件仓库知识图谱、依赖图、调用图与历史感知检索
代码 Agent 的长期记忆、规划、工具使用、失败恢复与可复现评测
编译优化感知的代码语义恢复、binary/source 对齐、debug 信息缺失恢复
Firmware/embedded repository reasoning 与跨版本漏洞追踪


- L0_直接相关 = 论文的主要问题、对象、方法或评测，直接落在你的三大类方向中
- L1_基础相关 = 漏洞、程序分析、形式化、二进制、软件演化等技术底座，但论文主问题不是你的 AI+安全主线
- L2_边界相关 = 多模态攻击、AI 鲁棒性、通用 Coding Agent、一般安全/隐私等；有研究启发，但是否阅读取决于具体威胁模型
- 不相关 = 仅在背景或泛化意义中出现 security、attack、root cause、reverse engineering 等词