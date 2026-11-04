"""
LightMPNNCalcJob：轻量、可等待、可失败的 Mock ProteinMPNN CalcJob
对接外部 bin/mock_mpnn.py 可执行脚本
"""
from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData
from aiida.common.datastructures import CalcInfo, CodeInfo


class LightMPNNCalcJob(CalcJob):
    """
    Mock ProteinMPNN CalcJob
    接口契约与真实 ProteinMPNN 对齐：
    输入：pdb_file + params
    输出：result.json（含 version / sequences / scores）
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("code", valid_type=__import__("aiida.orm").Code)
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("params", valid_type=Dict)
        # 必需输出
        spec.output("result", valid_type=Dict, required=True)
        # 退出码
        spec.exit_code(101, "ERROR_MOCK_FAILED", message="Mock MPNN 模拟运行失败")
        spec.exit_code(102, "ERROR_OUTPUT_MISSING", message="Mock MPNN 输出文件缺失")

    def prepare_for_submission(self, folder):
        # 写入输入文件
        params_dict = self.inputs.params.get_dict()
        folder.create_file_from_object("params.json", params_dict)
        folder.create_file_from_object("input.pdb", self.inputs.pdb_file.get_content())

        codeinfo = CodeInfo()
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.cmdline_params = []

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.retrieve_list = ["result.json"]

        return calcinfo
