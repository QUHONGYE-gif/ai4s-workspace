from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData
from aiida.engine.processes.calcjobs import CalcJobProcessSpec
import random


class MockMPNNCalcJob(CalcJob):
    """轻量模拟MPNN任务，C模块调试用，A侧就绪后弃用"""
    @classmethod
    def define(cls, spec: CalcJobProcessSpec):
        super().define(spec)
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("model_params", valid_type=Dict)
        spec.output("raw_data", valid_type=Dict)
        spec.exit_code(300, "SIMULATED_FAILED", message="模拟MPNN计算失败")

    def prepare_for_submission(self, folder):
        # 30%概率失败，用来测试重试；调试时可以改成 return self.exit_codes.SIMULATED_FAILED 固定失败
        if random.random() < 0.3:
            return self.exit_codes.SIMULATED_FAILED

        # 统一小样本：4条序列，对齐A侧规范
        out = Dict(dict={
            "sequences": [
                {"seq": "AAAA", "score": 0.82},
                {"seq": "LLLL", "score": 0.75},
                {"seq": "WWWW", "score": 0.61},
                {"seq": "RRRR", "score": 0.90},
            ]
        })
        self.out("raw_data", out)
        return None
