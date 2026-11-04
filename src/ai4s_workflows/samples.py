from aiida.orm import SinglefileData, QueryBuilder
from .calcjobs import LightMPNNCalcJob
from .workflows import ProteinMPNNFilterWorkChain


def make_test_pdb() -> SinglefileData:
    """生成测试PDB节点，用于mock样例"""
    return SinglefileData.from_string("TEST PDB\nATOM 1 N ALA A 1")


def count_mpnn_launches(wc_pk: int):
    """
    统计该workchain下真实提交的LightMPNNCalcJob数量
    验收重算证据：重筛选返回0，证明没有新启动MPNN
    """
    qb = QueryBuilder()
    qb.append(ProteinMPNNFilterWorkChain, filters={"id": wc_pk}, tag="wc")
    qb.append(LightMPNNCalcJob, with_incoming="wc")
    return qb.count()
