terraform {
  required_providers {
    coder = {
      source  = "coder/coder"
      version = "2.19.0"
    }
    docker = {
      source  = "kreuzwerker/docker"
      version = "3.9.0"
    }
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

variable "seed_path" {
  type        = string
  description = "Host directory containing a public Git repository.bundle"
}

variable "workspace_image" {
  type    = string
  default = "ai4s-workspace:server-0.1.0"
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

resource "coder_agent" "dev" {
  arch = data.coder_provisioner.me.arch
  os   = "linux"
  dir  = "/home/coder/ai4s-workspace"
  env = {
    AI4S_BRANCH         = "dev-${data.coder_workspace_owner.me.name}"
    AI4S_GIT_NAME       = data.coder_workspace_owner.me.name
    AI4S_GIT_EMAIL      = data.coder_workspace_owner.me.email
    AI4S_REPOSITORY_URL = "https://github.com/QUHONGYE-gif/ai4s-workspace.git"
  }
}

resource "coder_script" "repository" {
  agent_id           = coder_agent.dev.id
  display_name       = "Initialize personal repository"
  script             = file("${path.module}/startup.sh")
  run_on_start       = true
  start_blocks_login = true
}

# Fixed, owner-only paths: no wildcard domain or host port publication required.
# Members start their own application in the existing workspace container.
resource "coder_app" "preview" {
  agent_id     = coder_agent.dev.id
  slug         = "preview"
  display_name = "开发预览"
  url          = "http://localhost:3000"
  share        = "owner"
  subdomain    = false
  open_in      = "tab"
  order        = 1
  tooltip      = "启动个人开发服务（3000 端口）后打开；无需提交或合并代码。"
}

resource "coder_app" "analysis" {
  agent_id     = coder_agent.dev.id
  slug         = "analysis"
  display_name = "分析页面"
  url          = "http://localhost:8501"
  share        = "owner"
  subdomain    = false
  open_in      = "tab"
  order        = 2
  tooltip      = "启动个人分析服务（8501 端口）后打开；默认仅工作区本人可访问。"
}

resource "docker_volume" "home" {
  name = "ai4s-personal-${data.coder_workspace.me.id}-home"
  lifecycle {
    ignore_changes = all
  }
}

resource "docker_container" "workspace" {
  count = data.coder_workspace.me.start_count
  name  = "ai4s-personal-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"
  image = var.workspace_image
  user  = "0:0"

  # Agents stay on the Docker network even when members use an external HTTPS URL.
  entrypoint = ["sh", "-c", replace(coder_agent.dev.init_script, data.coder_workspace.me.access_url, "http://coder:7080")]
  env        = ["CODER_AGENT_TOKEN=${coder_agent.dev.token}", "HOME=/home/coder"]
  memory     = 1024
  cpu_period = 100000
  cpu_quota  = 100000

  networks_advanced {
    name = "ai4s-server"
  }

  volumes {
    container_path = "/home/coder"
    volume_name    = docker_volume.home.name
  }
  volumes {
    container_path = "/opt/ai4s-seed"
    host_path      = var.seed_path
    read_only      = true
  }
  volumes {
    container_path = "/shared"
    volume_name    = "ai4s-server_shared"
  }
  labels {
    label = "ai4s.project"
    value = "ai4s-personal"
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
}
