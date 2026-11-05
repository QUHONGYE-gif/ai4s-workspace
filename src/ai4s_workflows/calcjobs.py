import json

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
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("params", valid_type=Dict)
        spec.inputs["metadata"]["options"]["resources"].default = {
            "num_machines": 1, "num_mpiprocs_per_machine": 1
        }
        spec.inputs["metadata"]["options"]["max_wallclock_seconds"].default = 3600
        spec.inputs["metadata"]["options"]["parser_name"].default = "ai4s.light-mpnn"

        spec.output("result", valid_type=Dict, required=True)
        spec.exit_code(101, "MOCK_RUNTIME_FAIL", message="Mock MPNN运行失败或未生成result.json")
        spec.exit_code(102, "INVALID_RESULT_JSON", message="result.json不是有效的JSON对象")

    def prepare_for_submission(self, folder):
        codeinfo = CodeInfo()
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.cmdline_params = []

        calcinfo = CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.retrieve_list = ["result.json"]

        with folder.open("params.json", "w", encoding="utf-8") as handle:
            json.dump(self.inputs.params.get_dict(), handle)
        with folder.open("input.pdb", "w", encoding="utf-8") as handle:
            handle.write(self.inputs.pdb_file.get_content())

        return calcinfo

