from aiida.engine import WorkChain, ToContext
from aiida.orm import Dict, SinglefileData
from .calcjobs import LightMPNNCalcJob

SUPPORTED_VERSIONS = ["v1.0", "v1.1"]
MAX_RETRY = 2


class ProteinMPNNFilterWorkChain(WorkChain):
    """
    C模块：编排 生成→校验→筛选两阶段工作流
    1.推理参数mpnn_params，筛选参数filter_params完全分离
    2.可选输入existing_mpnn_result：重算场景直接复用上游输出，跳过MPNN提交
    3.门禁校验通过后才进入筛选；最多2次重试
    4.输出严格遵守公共接口：selected_sequences / sample_table / selection_report
    """
    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("code")
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("mpnn_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict)
        spec.input("existing_mpnn_result", valid_type=Dict, required=False)

        spec.output("selected_sequences", valid_type=Dict)
        spec.output("sample_table", valid_type=Dict)
        spec.output("selection_report", valid_type=Dict)

        spec.exit_code(201, "VERSION_NOT_SUPPORTED", message="MPNN版本不在支持白名单")
        spec.exit_code(202, "MAX_RETRY_REACHED", message="达到最大重试次数，任务终止")
        spec.exit_code(203, "MISSING_MPNN_OUTPUT", message="MPNN输出缺失artifacts")
        spec.exit_code(204, "INVALID_ARTIFACT_SCHEMA", message="产物schema_version不匹配ai4s‑artifacts‑1")

        # AiiDA2.9.4标准outline，按顺序执行步骤，无装饰器
        spec.outline(
            cls.initialize_ctx,
            cls.maybe_skip_inference,
            cls.submit_mpnn,
            cls.on_mpnn_done,
            cls.run_filter,
        )

    def initialize_ctx(self):
        self.ctx.retry_count = 0
        self.ctx.model_launches = 0
        self.ctx.mpnn_calc = None

    def maybe_skip_inference(self):
        """如果传入existing_mpnn_result，直接保存结果，跳转到on_mpnn_done"""
        if "existing_mpnn_result" in self.inputs:
            self.ctx.mpnn_result = self.inputs.existing_mpnn_result
            return self.next(self.on_mpnn_done)

    def submit_mpnn(self):
        builder = LightMPNNCalcJob.get_builder()
        builder.code = self.inputs.code
        builder.pdb_file = self.inputs.pdb_file
        builder.metadata.options = {
            "resources": {
                "num_machines": 1,
                "num_mpiprocs_per_machine": 1,
            }
        }
        builder.params = self.inputs.mpnn_params
        self.report(f"提交MPNN推理，第 {self.ctx.retry_count + 1} 次尝试")
        return ToContext(mpnn_calc=self.submit(builder))

    def on_mpnn_done(self):
        if "existing_mpnn_result" not in self.inputs:
            calc = self.ctx.mpnn_calc
            self.ctx.model_launches += 1

            if calc.is_failed:
                self.ctx.retry_count += 1
                if self.ctx.retry_count >= MAX_RETRY:
                    rep = {
                        "model_launches": self.ctx.model_launches,
                        "retry_attempt": self.ctx.retry_count,
                        "status": "failed_max_retry"
                    }
                    self.out("selection_report", Dict(rep))
                    return self.exit(self.exit_codes.MAX_RETRY_REACHED)

                self.report(f"MPNN任务失败，发起第 {self.ctx.retry_count+1} 次重试")
                return self.next(self.submit_mpnn)

            self.ctx.mpnn_result = calc.outputs.result

        mpnn_dict = self.ctx.mpnn_result.get_dict()

        if mpnn_dict.get("schema_version") != "ai4s-artifacts-1":
            rep = {
                "model_launches": self.ctx.model_launches,
                "retry_attempt": self.ctx.retry_count,
                "status": "invalid_schema"
            }
            self.out("selection_report", Dict(rep))
            return self.exit(self.exit_codes.INVALID_ARTIFACT_SCHEMA)

        artifacts = mpnn_dict.get("artifacts")
        if not artifacts or len(artifacts) == 0:
            rep = {
                "model_launches": self.ctx.model_launches,
                "retry_attempt": self.ctx.retry_count,
                "status": "missing_output"
            }
            self.out("selection_report", Dict(rep))
            return self.exit(self.exit_codes.MISSING_MPNN_OUTPUT)

        ver = mpnn_dict.get("version")
        if ver not in SUPPORTED_VERSIONS:
            rep = {
                "model_launches": self.ctx.model_launches,
                "retry_attempt": self.ctx.retry_count,
                "status": "unsupported_version"
            }
            self.out("selection_report", Dict(rep))
            return self.exit(self.exit_codes.VERSION_NOT_SUPPORTED)

    def run_filter(self):
        mpnn_data = self.ctx.mpnn_result.get_dict()
        f_params = self.inputs.filter_params.get_dict()
        threshold = f_params["score_threshold"]
        top_k = f_params["top_k"]

        artifact_entry = mpnn_data["artifacts"][0]
        sample_list = artifact_entry.get("samples", [])

        valid_samples = [s for s in sample_list if s["score"] <= threshold]
        valid_samples.sort(key=lambda x: (x["score"], x["sample_id"]))
        selected = valid_samples[:top_k]

        out_selected_sequences = {"entries": selected}
        out_sample_table = {
            "rows": selected,
            "score_threshold": threshold,
            "top_k": top_k
        }
        out_selection_report = {
            "model_launches": self.ctx.model_launches,
            "retry_attempt": self.ctx.retry_count,
            "selected_count": len(selected)
        }

        self.out("selected_sequences", Dict(out_selected_sequences))
        self.out("sample_table", Dict(out_sample_table))
        self.out("selection_report", Dict(out_selection_report))
        self.report("两阶段workchain全部执行完成")
