Usage: krr [STRATEGY] [OPTIONS]

| Section | Option | Short | Type | Description | Default |
|---------|--------|-------|------|-------------|---------|
| **Strategy** | `simple \| simple-limit` | | | Strategy for calculating resource recommendations. | |
| **Help** | `--help` | | | Show this message and exit. | |
| **Kubernetes Settings** | `--kubeconfig` | `-k` | TEXT | Path to kubeconfig file. If not provided, will attempt to find it. | None |
| | `--as` | | TEXT | Impersonate a user, just like `kubectl --as`. For example, system:serviceaccount:default:krr-account. | None |
| | `--as-group` | | TEXT | Impersonate a user inside of a group, just like `kubectl --as-group`. For example, system:authenticated. | None |
| | `--context`, `--cluster` | `-c` | TEXT | List of clusters to run on. By default, will run on the current cluster. Use --all-clusters to run on all clusters. | None |
| | `--all-clusters` | | | Run on all clusters. Overrides --context. | |
| | `--namespace` | `-n` | TEXT | List of namespaces to run on. By default, will run on all namespaces except 'kube-system'. | None |
| | `--resource` | `-r` | TEXT | List of resources to run on (Deployment, StatefulSet, DaemonSet, Job, Rollout, StrimziPodSet). By default, will run on all resources. Case insensitive. | None |
| | `--selector` | `-s` | TEXT | Selector (label query) to filter workloads. Applied to labels on the workload (e.g. deployment) not on the individual pod! Supports '=', '==', and '!='.(e.g. -s key1=value1,key2=value2). Matching objects must satisfy all of the specified label constraints. | None |
| **Prometheus Settings** | `--prometheus-url` | `-p` | TEXT | Prometheus URL. If not provided, will attempt to find it in kubernetes cluster | None |
| | `--prometheus-auth-header` | | TEXT | Prometheus authentication header. | None |
| | `--prometheus-headers` | `-H` | TEXT | Additional headers to add to Prometheus requests. Format as 'key: value', for example 'X-MyHeader: 123'. Trailing whitespaces will be stripped. | None |
| | `--prometheus-ssl-enabled` | | | Enable SSL for Prometheus requests. | |
| | `--prometheus-cluster-label` | `-l` | TEXT | The label in prometheus for your cluster.(Only relevant for centralized prometheus) | None |
| | `--prometheus-label` | | TEXT | The label in prometheus used to differentiate clusters. (Only relevant for centralized prometheus) | None |
| **Prometheus EKS Settings** | `--eks-managed-prom` | | | Adds additional signitures for eks prometheus connection. | |
| | `--eks-profile-name` | | TEXT | Sets the profile name for eks prometheus connection. | None |
| | `--eks-access-key` | | TEXT | Sets the access key for eks prometheus connection. | None |
| | `--eks-secret-key` | | TEXT | Sets the secret key for eks prometheus connection. | None |
| | `--eks-service-name` | | TEXT | Sets the service name for eks prometheus connection. | aps |
| | `--eks-managed-prom-region` | | TEXT | Sets the region for eks prometheus connection. | None |
| **Prometheus Coralogix Settings** | `--coralogix-token` | | TEXT | Adds the token needed to query Coralogix managed prometheus. | None |
| **Prometheus Openshift Settings** | `--openshift` | | | Connect to Prometheus with a token read from /var/run/secrets/kubernetes.io/serviceaccount/token - recommended when running KRR inside an OpenShift cluster | |
| **Recommendation Settings** | `--cpu-min` | | INTEGER | Sets the minimum recommended cpu value in millicores. | 10 |
| | `--mem-min` | | INTEGER | Sets the minimum recommended memory value in MB. | 100 |
| **Threading Settings** | `--max-workers` | `-w` | INTEGER | Max workers to use for async requests. | 10 |
| **Logging Settings** | `--formatter` | `-f` | TEXT | Output formatter (json, pprint, table, yaml, csv, csv-raw, html) | table |
| | `--verbose` | `-v` | | Enable verbose mode | |
| | `--quiet` | `-q` | | Enable quiet mode | |
| | `--logtostderr` | | | Pass logs to stderr | |
| | `--width` | | INTEGER | Width of the output. Will use console width by default. | None |
| **Output Settings** | `--show-cluster-name` | | | In table output, always show the cluster name even for a single cluster | |
| | `--exclude-severity` | | | Whether to include the severity in the output or not | True |
| | `--fileoutput` | | TEXT | Filename to write output to (if not specified, file output is disabled) | None |
| | `--fileoutput-dynamic` | | | Ignore --fileoutput and write files to the current directory in the format krr-{datetime}.{format} (e.g. krr-20240518223924.csv) | |
| | `--slackoutput` | | TEXT | Send to output to a slack channel, must have SLACK_BOT_TOKEN | None |
| **Publish Scan Settings** | `--publish_scan_url` | | TEXT | Sends the output to a robusta_runner instance | None |
| | `--start_time` | | TEXT | Start time of the scan | None |
| | `--scan_id` | | TEXT | A UUID scan identifier | None |
| **Strategy Settings** | `--history_duration`, `--history-duration` | | TEXT | The duration of the history data to use (in hours). | 336 |
| | `--timeframe-duration`, `--timeframe_duration` | | TEXT | The step for the history data (in minutes). | 1.25 |
| | `--cpu-percentile`, `--cpu_percentile` | | TEXT | The percentile to use for the CPU recommendation. | 95 |
| | `--memory_buffer_percentage`, `--memory-buffer-percentage` | | TEXT | The percentage of added buffer to the peak memory usage for memory recommendation. | 15 |
| | `--points-required`, `--points_required` | | TEXT | The number of data points required to make a recommendation for a resource. | 100 |
| | `--allow_hpa`, `--allow-hpa` | | | Whether to calculate recommendations even when there is an HPA scaler defined on that resource. | |
| | `--use_oomkill_data`, `--use-oomkill-data` | | | Whether to bump the memory when OOMKills are detected (experimental). | |
| | `--oom_memory_buffer_percentage`, `--oom-memory-buffer-percentage` | | TEXT | What percentage to increase the memory when there are OOMKill events. | 25 |
