"""Run or submit one ProteinMPNN CalcJob.

Example (unified small sample):
    python -m ai4s_tasks.submit --seed 37 --submit
"""

import argparse

from aiida import load_profile, orm
from aiida.engine import run_get_node, submit
from aiida.plugins import CalculationFactory

DEFAULT_PDB = "/opt/ai4s/proteinmpnn/releases/8907e667-py312-torch260cu124/examples/1CRN.pdb"


def build_inputs(options):
    builder = CalculationFactory("ai4s.proteinmpnn").get_builder()
    builder.code = orm.load_code(options.code)
    builder.pdb_file = orm.SinglefileData(file=options.pdb)
    builder.params = orm.Dict({
        "chains": options.chains,
        "num_sequences": options.num_sequences,
        "sampling_temperature": options.temperature,
        "seed": options.seed,
        "model_name": options.model_name,
        "batch_size": 1,
        "save_probabilities": not options.no_probabilities,
    })
    builder.metadata.label = options.label
    return builder


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdb", default=DEFAULT_PDB)
    parser.add_argument("--chains", default="A")
    parser.add_argument("--num-sequences", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--seed", type=int, required=True, help="Non-zero seed fixed before submission.")
    parser.add_argument("--model-name", default="v_48_020")
    parser.add_argument("--no-probabilities", action="store_true")
    parser.add_argument("--code", default="proteinmpnn-8907e667@localhost")
    parser.add_argument("--label", default="proteinmpnn-1crn")
    parser.add_argument("--submit", action="store_true", help="Hand over to the daemon instead of running here.")
    options = parser.parse_args()

    load_profile()
    builder = build_inputs(options)
    if options.submit:
        node = submit(builder)
        print(f"submitted pk={node.pk} uuid={node.uuid}")
        return
    _, node = run_get_node(builder)
    print(f"finished pk={node.pk} uuid={node.uuid} exit_status={node.exit_status} "
          f"cached_from={node.base.caching.get_cache_source()}")


if __name__ == "__main__":
    main()
