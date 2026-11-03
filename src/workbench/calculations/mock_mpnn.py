# Mock MPNN 计算任务，仅用于C模块逻辑调试，A侧交付真实CalcJob后替换
from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData

class MockMPNNCalcJob(CalcJob):
    """模拟ProteinMPNN模型：输入PDB，输出3条带分数的候选序列"""
    @classmethod
    def define(cls, spec):
        super().define(spec)
        # 输入端口（和队友A侧真实CalcJob保持一致，对接时不用改WorkChain）
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("params", valid_type=Dict)
        # 输出端口（同上，接口契约）
        spec.output("result", valid_type=Dict, required=True)

    def run(self):
        # 模拟计算耗时，输出固定测试序列（3条，不同分数）
        test_sequences = [
            {"seq": "AAA", "score": 0.92},
            {"seq": "BBB", "score": 0.81},
            {"seq": "CCC", "score": 0.65},
        ]
        self.out("result", Dict({
            "version": self.inputs.params["version"],
            "sequences": test_sequences
        }).store())
