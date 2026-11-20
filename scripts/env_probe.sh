#!/usr/bin/env bash
# 盘点共用模型环境的真实版本、体积与依赖，供 5.0 依赖对照表使用。
# 在 Coder 容器里运行：bash scripts/env_probe.sh

set -u
OUT="${1:-$HOME/env-probe}"
mkdir -p "$OUT"

probe() {
  local name="$1" dir="$2"
  echo "===== $name ====="
  if [ ! -e "$dir" ]; then
    echo "路径不存在: $dir"
    return
  fi
  local real
  real=$(readlink -f "$dir")
  echo "path=$dir"
  echo "real=$real"
  du -sh "$real" 2>/dev/null | awk '{print "size="$1}'
  du -sb "$real" 2>/dev/null | awk '{print "size_bytes="$1}'

  local py="$real/bin/python"
  if [ -x "$py" ]; then
    "$py" - <<'PY' 2>/dev/null || echo "python_check=failed"
import sys
print("python=" + sys.version.split()[0])
try:
    import torch
    print("torch=" + torch.__version__)
    print("cuda_build=" + str(torch.version.cuda))
    print("cuda_available=" + str(torch.cuda.is_available()))
except Exception as error:
    print("torch=missing(" + type(error).__name__ + ")")
try:
    import numpy
    print("numpy=" + numpy.__version__)
except Exception:
    print("numpy=missing")
PY
    "$py" -m pip freeze 2>/dev/null | wc -l | awk '{print "package_count="$1}'
    "$py" -m pip freeze 2>/dev/null > "$OUT/${name}-pip-freeze.txt"
    echo "freeze_file=$OUT/${name}-pip-freeze.txt"
  else
    echo "python=missing($py)"
  fi
}

probe proteinmpnn /opt/ai4s/proteinmpnn/current
probe boltz /opt/ai4s/boltz/current
probe rfdiffusion /opt/ai4s/rfdiffusion/current

echo "===== 宿主信息 ====="
echo "disk=$(df -h "$HOME" | tail -1 | awk '{print $2" total, "$4" free"}')"
echo "gpu=$(nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader | head -1)"
echo "cuda_driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"

echo "===== 个人环境 ====="
for v in "$HOME"/.venvs/*/; do
  [ -d "$v" ] || continue
  echo "venv=$v python=$("$v/bin/python" -V 2>&1 | awk '{print $2}') size=$(du -sh "$v" 2>/dev/null | awk '{print $1}')"
done
echo "uv_cache=$(du -sh "$HOME"/.cache/uv 2>/dev/null | awk '{print $1}')"
echo "pip_cache=$(du -sh "$HOME"/.cache/pip 2>/dev/null | awk '{print $1}')"
echo "conda=$(command -v conda || echo none)"
echo "done. 结果目录: $OUT"
