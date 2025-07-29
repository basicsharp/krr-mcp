# User Guide

Complete guide to using the KRR MCP Server with AI assistants for safe Kubernetes resource optimization.

## 🎯 Overview

The KRR MCP Server enables you to optimize Kubernetes resources through natural language conversations with AI assistants like Claude. This guide shows you how to use all features safely and effectively.

### Key Principles

1. **Safety First**: Every change requires your explicit approval
2. **Transparency**: You see exactly what will change before it happens  
3. **Reversibility**: All changes can be rolled back
4. **Natural Language**: Talk to your cluster through AI

## 🚀 Getting Started

### Prerequisites

Before starting, ensure you have:
- ✅ KRR MCP Server installed ([Installation Guide](installation.md))
- ✅ Claude Desktop or another MCP client configured
- ✅ Access to a Kubernetes cluster with Prometheus
- ✅ Basic understanding of Kubernetes resources

### First Steps

1. **Start with a non-production cluster** for testing
2. **Verify your setup** with basic commands
3. **Understand the safety features** before making changes
4. **Practice the workflow** with dry-run operations

## 💬 Basic Usage Patterns

### Pattern 1: Analysis Only

Start with read-only analysis to understand your cluster:

```
"Show me resource usage across all namespaces"
```

```
"What are the top 10 workloads that could benefit from optimization?"
```

```
"Analyze CPU and memory usage patterns in the development namespace"
```

### Pattern 2: Exploration with Preview

Explore optimizations without making changes:

```
"What would happen if I optimized the web-app deployment?"
```

```
"Show me the impact of applying medium strategy recommendations to the api namespace"
```

```
"Preview resource changes for all deployments in staging"
```

### Pattern 3: Safe Application

Apply changes with full safety controls:

```
"I want to optimize my web-app deployment. Show me the changes, get my approval, then apply them."
```

```
"Apply resource optimizations to the development namespace with medium strategy"
```

```
"Help me optimize costs in the staging environment - but ask for confirmation first"
```

## 🛡️ Safety Features in Action

### Confirmation Workflow

Every cluster modification follows this safe pattern:

#### 1. Analysis Phase (Safe)
- AI analyzes your cluster using krr
- Resource usage patterns identified
- Recommendations generated
- **No cluster changes made**

#### 2. Preview Phase (Safe)
- Shows exactly what would change
- Impact analysis provided
- Risk assessment performed
- **No cluster changes made**

#### 3. Confirmation Phase (Required)
- AI presents detailed confirmation prompt
- You review and approve/reject
- Safety assessment included
- **No cluster changes until you approve**

#### 4. Execution Phase (Controlled)  
- Changes applied with rollback preparation
- Progress monitoring
- Complete audit trail
- **Changes made only after approval**

### Example Workflow

**You say:** *"Optimize the web-app deployment in the production namespace"*

**AI Analysis Response:**
```
I'll help you optimize the web-app deployment safely. Let me start by analyzing current usage...

Resource Analysis Complete:
- Deployment: web-app (namespace: production)
- Current CPU: 100m (underutilized - avg 25m)  
- Current Memory: 128Mi (overutilized - avg 180Mi)
- Recommendation: Increase memory to 256Mi, decrease CPU to 50m

Would you like me to preview these changes?
```

**You say:** *"Yes, show me the preview"*

**AI Preview Response:**
```
Change Preview for web-app deployment:

Resource Changes:
- CPU Request: 100m → 50m (-50%)
- Memory Request: 128Mi → 256Mi (+100%)

Impact Analysis:
- Pod restarts required: Yes (rolling update)
- Replicas affected: 3
- Risk level: MEDIUM (production namespace, memory increase)
- Estimated monthly cost: -$15 (CPU savings > memory cost)

Safety Assessment:
⚠️  Production namespace detected - enhanced safety protocols active
✅  Changes within safe limits (<500% change)
✅  Critical workload patterns not detected
⚠️  Memory increase may cause temporary resource pressure

Would you like me to request confirmation to apply these changes?
```

**You say:** *"Yes, apply these changes"*

**AI Confirmation Request:**
```
RESOURCE OPTIMIZATION CONFIRMATION

The following changes will be applied to cluster 'production-cluster':

Deployment: web-app (namespace: production)
- CPU Request: 100m → 50m (-50%)
- Memory Request: 128Mi → 256Mi (+100%)

Impact Analysis:
- Pods affected: 3
- Rolling restart required: Yes
- Risk level: MEDIUM
- Estimated completion time: 2-3 minutes
- Monthly cost impact: -$15

Safety Information:
- Rollback snapshot: web-app-20250129-143052
- Rollback retention: 7 days
- Confirmation expires: 5 minutes

Do you want to proceed with these changes? (Reply 'yes' to confirm)
```

**You say:** *"yes"*

**AI Execution Response:**
```
✅ Confirmation received. Applying changes...

Execution Progress:
[████████████████████████████████] 100%

Results:
✅ Deployment updated successfully
✅ Rolling update completed (2m 15s)
✅ All pods healthy and ready
✅ Rollback snapshot created: web-app-20250129-143052

Summary:
- CPU request reduced: 100m → 50m  
- Memory request increased: 128Mi → 256Mi
- 3 pods successfully updated
- Change ID: ch_20250129_143055_web-app

You can rollback these changes anytime with: "Rollback change ch_20250129_143055_web-app"
```

## 🔍 Common Use Cases

### 1. Cost Optimization

**Scenario**: Reduce cloud costs by optimizing overprovisioned resources

```
User: "Help me reduce costs in my production cluster. Show me the biggest savings opportunities."

AI: I'll analyze your cluster for cost optimization opportunities...

[Analysis results showing top savings opportunities]

User: "Focus on the top 3 deployments. What would I save if I optimized them?"

AI: [Detailed cost analysis and projected savings]

User: "That looks good. Apply optimizations to deployment 'api-server' first."

AI: [Safety workflow: preview → confirmation → execution]
```

### 2. Performance Optimization

**Scenario**: Fix performance issues by right-sizing resources

```
User: "The checkout-service is running slowly. Can you check if it needs more resources?"

AI: Let me analyze the checkout-service resource usage...

Current Analysis:
- CPU: Frequently hitting limits (throttling detected)
- Memory: Well within limits
- Recommendation: Increase CPU from 200m to 500m

User: "Yes, that makes sense. Apply the CPU increase."

AI: [Safety workflow with performance-focused impact analysis]
```

### 3. Bulk Optimization

**Scenario**: Optimize an entire namespace or cluster

```
User: "I want to optimize all deployments in the development namespace using the aggressive strategy."

AI: I'll analyze all deployments in the development namespace with aggressive optimization...

Found 12 deployments that can be optimized:
- 8 are over-provisioned (potential savings: $200/month)
- 4 are under-provisioned (performance improvements needed)

User: "Show me a summary of all changes before applying."

AI: [Comprehensive change summary with batch operation details]

User: "Apply all changes but do them in small batches to minimize risk."

AI: [Staged execution with progress updates]
```

### 4. Monitoring and Maintenance

**Scenario**: Regular cluster health and optimization maintenance

```
User: "Give me a weekly optimization report for all namespaces."

AI: [Comprehensive cluster health and optimization report]

User: "What changes were made last week? Any issues?"

AI: [Execution history with success/failure analysis]

User: "Check if the optimization we did to web-app last Tuesday is still working well."

AI: [Post-optimization analysis and recommendations]
```

## 🛠️ Advanced Features

### Filtering and Targeting

Control which resources are analyzed and optimized:

```
"Optimize only CPU-bound workloads in the api namespace"
```

```
"Show memory optimization opportunities for deployments starting with 'web-'"
```

```
"Analyze statefulsets but exclude anything with 'database' in the name"
```

### Strategy Selection

Choose the optimization approach that fits your needs:

```
"Use simple strategy for production workloads" (conservative)
```

```
"Apply medium strategy to staging deployments" (balanced)
```

```
"Use aggressive strategy for development namespace" (maximum optimization)
```

### Risk Management

Control risk levels and safety measures:

```
"Only show me low-risk optimizations for production"
```

```
"I want to apply these changes but with extra safety checks"
```

```
"Enable canary deployment for this optimization"
```

## 📊 Understanding Recommendations

### Recommendation Types

#### CPU Optimizations
- **Over-provisioned**: CPU limits too high, wasteful
- **Under-provisioned**: CPU limits too low, throttling
- **Right-sized**: CPU allocation matches usage

#### Memory Optimizations  
- **Over-provisioned**: Memory limits too high, wasteful
- **Under-provisioned**: Memory limits too low, OOM risk
- **Right-sized**: Memory allocation matches usage

### Recommendation Confidence

- **High Confidence**: Based on consistent usage patterns
- **Medium Confidence**: Some variation in usage patterns
- **Low Confidence**: Limited data or high variability

### Safety Indicators

- 🟢 **Low Risk**: Minor changes, non-critical workloads
- 🟡 **Medium Risk**: Moderate changes, some impact possible
- 🔴 **High Risk**: Major changes, production workloads affected
- ⚫ **Critical Risk**: Changes blocked by safety rules

## 🔄 Rollback Operations

### When Rollbacks Are Needed

- Performance degradation after optimization
- Resource constraints causing issues  
- Unexpected application behavior
- Compliance or policy violations

### Rollback Examples

```
"Rollback the changes I made to web-app this morning"
```

```
"I need to undo the optimization to the api-server deployment"
```

```
"Show me all changes from yesterday and rollback the problematic ones"
```

```
"Emergency rollback: revert all changes from the last 2 hours"
```

### Rollback Process

1. **Identify Changes**: List recent optimizations
2. **Select Target**: Choose specific changes to revert
3. **Safety Check**: Verify rollback won't cause issues
4. **Confirmation**: Approve rollback operation
5. **Execution**: Apply original resource settings
6. **Verification**: Confirm resources are restored

## 📈 Monitoring and Maintenance

### Regular Health Checks

Schedule regular optimization reviews:

```
"Weekly optimization review: show me new opportunities"
```

```
"Are there any performance issues from last week's changes?"
```

```
"Monthly cost optimization report for all namespaces"
```

### Monitoring Recommendations

1. **Set up alerts** for resource constraint issues
2. **Review optimization impact** after 24-48 hours
3. **Monitor cost changes** in your cloud billing
4. **Track application performance** metrics
5. **Maintain rollback readiness** for quick recovery

## ⚠️ Safety Best Practices

### Do's

- ✅ **Start with development/staging** clusters
- ✅ **Review every confirmation** carefully
- ✅ **Test optimizations** with low-risk workloads first
- ✅ **Monitor applications** after changes
- ✅ **Keep rollback capabilities** ready
- ✅ **Understand your workloads** before optimizing
- ✅ **Use appropriate strategies** for each environment

### Don'ts

- 🚫 **Don't optimize production** without testing first
- 🚫 **Don't ignore safety warnings** or confirmation prompts
- 🚫 **Don't apply bulk changes** without understanding impact
- 🚫 **Don't optimize during peak traffic** or deployments
- 🚫 **Don't skip monitoring** after optimizations
- 🚫 **Don't optimize critical workloads** without extra caution
- 🚫 **Don't rush the confirmation process**

### Emergency Procedures

If something goes wrong:

1. **Stay calm** - rollback capabilities are always available
2. **Identify the issue** - check application health first
3. **Use rollback** - "Emergency rollback: revert latest changes"
4. **Verify restoration** - confirm applications are healthy
5. **Investigate cause** - review what went wrong
6. **Learn and improve** - adjust safety settings if needed

## 🆘 Troubleshooting

### Common Issues

#### "No recommendations found"
- Check if Prometheus is collecting metrics
- Verify workloads have sufficient historical data  
- Ensure krr strategy is appropriate for your workload patterns

#### "Changes were blocked by safety rules"
- Review the safety assessment details
- Consider using a more conservative strategy
- Check if workloads match critical workload patterns

#### "Rollback failed"
- Verify original resources are available in rollback snapshot
- Check cluster capacity and resource constraints
- Use kubectl directly if automated rollback fails

#### "Optimization didn't improve performance"
- Allow 24-48 hours for application adaptation
- Check if other bottlenecks exist (network, storage, etc.)
- Consider rolling back and using different optimization strategy

### Getting Help

1. **Check the AI's explanations** - they include troubleshooting hints
2. **Review execution history** - `"Show me recent changes and their status"`
3. **Check system logs** - Enable debug mode for detailed information
4. **Use diagnostic tools** - `"Generate a diagnostic report"`
5. **Consult documentation** - Check [API Reference](api/README.md) for details
6. **Contact support** - Report issues on [GitHub](https://github.com/your-org/krr-mcp/issues)

## 📚 Next Steps

Once you're comfortable with basic usage:

1. **Explore advanced features** - Custom strategies, bulk operations
2. **Set up automation** - Regular optimization schedules
3. **Integrate monitoring** - Connect with your observability stack
4. **Share knowledge** - Train your team on safe optimization practices
5. **Contribute back** - Share improvements and feedback

## 🔗 Related Resources

- **[Installation Guide](installation.md)** - Setup and configuration
- **[Safety Guide](safety.md)** - Understanding safety features  
- **[API Reference](api/README.md)** - Complete tool documentation
- **[Deployment Guide](deployment.md)** - Production deployment
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

---

**Remember**: The KRR MCP Server is designed to make optimization both powerful and safe. When in doubt, start with analysis, use previews extensively, and always test in non-production environments first. 