# Mock MPNN 计算任务，仅用于C模块逻辑调试，A侧交付真实CalcJob后替换
from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData
from aiida.common import CalcInfo

class MockMPNNCalcJob(CalcJob):
    """模拟ProteinMPNN模型：输入PDB，输出3条带分数的候选序列"""
    @classmethod
    def define(cls, spec):
        super().define(spec)
        # 输入端口（和队友A侧真实CalcJob保持一致，对接时不用改WorkChain）
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("params", valid_type=Dict)
        # 【可选调试开关】控制本次mock是否模拟失败，用来测重试
        spec.input("mock_fail", valid_type=Dict, required=False, default=lambda: Dict({"fail": False}))
        # 输出端口（同上，接口契约）
        spec.output("result", valid_type=Dict, required=True)
        # 失败退出码
        spec.exit_code(200, "MOCK_FAILED", message="Mock模拟MPNN计算失败")

    def prepare_for_submission(self, folder):
        calcinfo = CalcInfo()
        calcinfo.codes_info = []
        # 我们不真的写脚本跑，直接在 retrieve 阶段把结果注入
        # 真正的mock逻辑放在 parse 里
        return calcinfo

    def parse(self, folder):
        fail_flag = self.inputs.mock_fail["fail"]
        if fail_flag:
            return self.exit_codes.MOCK_FAILED

        test_sequences = [
            {"seq": "AAA", "score": 0.92},
            {"seq": "BBB", "score": 0.81},
            {"seq": "CCC", "score": 0.65},
        ]
        self.out("result", Dict({
            "version": self.inputs.params["version"],
            "sequences": test_sequences
        }).store())
