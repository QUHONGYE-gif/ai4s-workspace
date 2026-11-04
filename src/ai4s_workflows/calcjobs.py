from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData
from aiida.common.datastructures import CalcInfo, CodeInfo


class LightMPNNCalcJob(CalcJob):
    """
    C模块自建轻量可等待、可失败CalcJob，对接bin/mock_mpnn.py
    接口对齐A侧真实ProteinMPNN CalcJob
    """
    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("code")
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("params", valid_type=Dict)
        spec.output("result", valid_type=Dict, required=True)
        spec.exit_code(101, "MOCK_RUNTIME_FAIL", message="Mock MPNN模拟运行失败")

    def prepare_for_submission(self, folder):
        codeinfo = CodeInfo()
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.cmdline_params = []

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.retrieve_list = ["result.json"]

        # 写入输入文件
        folder.create_file_from_object("params.json", self.inputs.params.get_dict())
        folder.create_file_from_object("input.pdb", self.inputs.pdb_file.get_content())
        return calcinfo
