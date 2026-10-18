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

variable "project_path" {
  type        = string
  description = "Absolute host path of this repository"
}

variable "deployment_prefix" {
  type    = string
  default = "ai4s-local"
}

variable "workspace_image" {
  type    = string
  default = "ai4s-workspace:0.1.0"
}

variable "workspace_user" {
  type        = string
  default     = null
  description = "Container user override; 0:0 maps to the host user in rootless Docker"
}

variable "access_port" {
  type    = number
  default = 7080
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

resource "coder_agent" "dev" {
  arch = data.coder_provisioner.me.arch
  os   = "linux"
  dir  = "/workspace/project"
}

resource "docker_volume" "home" {
  name = "${var.deployment_prefix}-${data.coder_workspace.me.id}-home"
  lifecycle {
    ignore_changes = all
  }
}

resource "docker_container" "workspace" {
  count = data.coder_workspace.me.start_count
  name  = "${var.deployment_prefix}-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"
  image = var.workspace_image
  user  = var.workspace_user

  # Agents use the private Docker DNS name; the browser uses localhost.
  entrypoint = ["sh", "-c", replace(replace(coder_agent.dev.init_script, "localhost:${var.access_port}", "coder:7080"), "127.0.0.1:${var.access_port}", "coder:7080")]
  env        = concat(["CODER_AGENT_TOKEN=${coder_agent.dev.token}"], var.workspace_user == "0:0" ? ["HOME=/home/coder"] : [])
  memory     = 2048
  cpu_period = 100000
  cpu_quota  = 200000

  networks_advanced {
    name = var.deployment_prefix
  }

  volumes {
    container_path = "/home/coder"
    volume_name    = docker_volume.home.name
  }
  volumes {
    container_path = "/workspace/project"
    host_path      = var.project_path
  }
  volumes {
    container_path = "/shared"
    volume_name    = "${var.deployment_prefix}_shared"
  }
  labels {
    label = "ai4s.project"
    value = var.deployment_prefix
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
}
