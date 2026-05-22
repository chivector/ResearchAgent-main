# PayloadView 的理论支撑：义务感知的最小充分载荷

## 1. 问题定位

在科学多 Agent 系统中，上下文不是被动背景，而是会改变推理轨迹的控制变量。把完整 dossier 输入给每个 Agent 看似保守，但会同时增加 token 成本、注意力稀释和领域污染风险。FrontierScience-Research 这类任务尤其依赖隐含评分义务：公式、变量、边界条件、排除项、推导步骤和结论形态都可能影响最终得分。因此，目标不是“上下文越多越好”，也不是“摘要越短越好”，而是为每次 Agent 调用编译一个满足当前义务的最小充分 PayloadView。

我们把底层结构称为 OC-HMG，即 Obligation-Conditioned Hierarchical Memory Graph；把选择层称为 OPC，即 Obligation-aware Payload Compiler。它们共同把上下文管理表述为一个受约束集合选择问题，而不是普通 RAG、普通摘要或 prompt trimming。

## 2. 形式化定义

设第 t 步的全局记忆图为：

```text
Gₜ = (Mₜ, Eₜ),    Mₜ = {m₁, …, mₙ}
```

其中每个记忆原子为：

```text
mᵢ = (idᵢ, τᵢ, cᵢ, sᵢ, pᵢ, dᵢ, oᵢ, rᵢ, κᵢ, δᵢ)
```

τᵢ 表示原子类型，例如 obligation、constraint、evidence、claim、derivation、critic_finding；cᵢ 是内容；pᵢ 是来源；dᵢ 是依赖集合；oᵢ 是服务的义务集合；rᵢ 是角色相关性；κᵢ 是 token 成本；δᵢ 是干扰风险。sᵢ 是 support license，满足如下许可序：

```text
prohibited < unsupported < speculative < plausible < supported < verified
```

一次 Agent 调用定义为：

```text
Iₐ = (a, qₐ, Oₐ, Kₐ, Bₐ)
```

a 是 Agent 角色，qₐ 是当前子任务，Oₐ 是必须满足的义务集合，Kₐ 是运行时契约，Bₐ 是预算。PayloadView 是从全局记忆图编译出的子图及其渲染：

```text
Cₐ ⊆ Mₜ,    Vₐ = Render(Cₐ, Iₐ)
```

这里 Cₐ 不是持久摘要，而是同一张记忆图在一次具体调用下的角色化视图。

## 3. 最小充分性

给定调用 Iₐ，如果 Cₐ 满足以下约束，则称其相对于当前图规则是充分的：

1. 义务覆盖：每个 active obligation 要么由运行时任务定义覆盖，要么由非 obligation 原子明确服务。
2. 支持闭包：每个可写入答案的 claim 必须有可见的 evidence、derivation 或 task output 支持路径。
3. 依赖闭包：公式、变量、单位、边界条件和前置推导不能被拆散。
4. 角色许可：Writer 和 FormalDeriver 只能把 supported 或 verified 内容作为 allowed claim。
5. 污染控制：prohibited、unsupported、speculative 内容只能进入 warning、rejected alternative 或 verification 视图。

在当前候选族 𝒞ₐ 和 verifier 下，局部最小充分 PayloadView 可写为：

```text
Cₐ* = argmin Cost(C)
      subject to C ∈ 𝒞ₐ and Verify(C, Iₐ) = true
```

这个定义刻意使用“局部”。当前系统只在 minimal、support_complete、dependency_complete、critic_safe、broad_fallback 及有限 repair 轨迹中搜索，不枚举全部子图，因此它追求的是可解释、低成本、可复现实验的近似最优。

## 4. 编译目标

Payload 编译可以写成约束优化形式：

```text
minimize    Cost(C) + λ Risk(C)
subject to  Coverage(C, Oₐ) = 1
            SupportClosure(C, a) = 1
            DependencyClosure(C, a) = 1
            RoleLicense(C, a) = 1
```

实际系统采用更轻量的打分近似：

```text
Score(C) =
  α Coverage(C, Oₐ)
+ β Support(C)
+ ρ Dependency(C)
+ η RoleFit(C, a)
+ ξ StateBoost(C, Sₜ)
- λ Cost(C)
- γ DistractorRisk(C)
```

其中静态部分是 role profile、license gate 和 atom/edge 语义；动态部分是当前状态 Sₜ，例如 pending obligations、proof gaps、critic findings、support pressure、dependency pressure、task type 和 domain。这样既避免完全手工规则，也避免引入高成本的学习式 ranker。

## 5. 理论命题与证明草图

**命题 1：Full dossier 不是理论最优输入。**  
若存在至少一个与当前任务无关、且 κᵢ > 0 或 δᵢ > 0 的 atom，删除它不会降低义务覆盖、支持闭包或依赖闭包，却会降低 cost 或 risk。因此 full dossier 可作为保守审计视图，但不是最小充分目标下的默认最优解。

**命题 2：通过 verifier 的最小候选是局部最小充分载荷。**  
候选集合由 OPC 生成，verifier 将候选划分为 passed 和 failed。系统在 passed candidates 中选择 Cost 最小者，所以在已生成候选空间内不存在更低成本且同样通过验证的视图。这不等价于全局最优，因为系统没有枚举 2ⁿ 个子图。

**命题 3：support-license gate 降低 unsupported claim 泄漏。**  
Writer 的 allowed claims 只允许 supported 或 verified。低许可 claim 被排除到 warnings 或 rejected alternatives 中。该机制不能完全阻止模型生成幻觉，但能减少系统显式提供未支持主张的机会，并把风险前移到可审计的图规则中。

**命题 4：状态调控打分是受约束选择的低成本近似。**  
精确子图选择代价过高。OPC 用硬门控处理不可违反约束，用 atom-level scoring 表示软偏好，再用 support/dependency repair 补齐闭包缺口。这牺牲全局最优性，换取线性或近线性的运行成本和可解释日志。

## 6. 实验支撑与边界

real_q1 的当前结果提供了经验支撑：13 个 PayloadView 全部通过 verifier，fail-soft count 为 0；总 legacy token cost 为 369,437，总 rendered token cost 为 166,204，节省 203,233，节省率 55.0%；Writer 侧节省 72.8%；LLM-as-judge 得分为 9.2/10。

这些结果说明，OPC 在该题上减少了重复上下文注入，同时没有破坏当前图规则要求的输入充分性，并且保留了主要解题质量。但 payload_verified=true 只表示“满足当前 verifier 的载荷充分性”，不等于最终答案必然满分。当前主要边界是公式级 obligation 建模仍不够细：如果“必须显式写出某公式”没有进入图中，compiler 就无法主动保留它。下一步应增强 formula-level obligation atoms，使 verifier 能检查关键公式、比较关系和边界条件是否被可写材料覆盖。
