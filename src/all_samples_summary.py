import argparse
import pathlib
import os
import sys
from src.misc_functions import try_except_continue_on_fail
from src.misc_functions import fasta_to_dct

__author__ = 'Colin Anthony'


class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
    pass


def main(project_path, all_samples_consens_seqs, ref_seq, run_name):

    print("aligning consensus sequence from all samples\n")
    tmp_file = pathlib.Path(project_path, "temp_aligned_file.fasta")
    mafft_cmd = f"mafft {str(all_samples_consens_seqs)} > {str(tmp_file)}"

    print(mafft_cmd)
    run = try_except_continue_on_fail(mafft_cmd)
    if not run:
        print(f"could not align {all_samples_consens_seqs}")
        sys.exit("exiting")
    else:
        all_samples_consens_seqs.unlink()
        os.rename(tmp_file, str(all_samples_consens_seqs))

        # calculate coverage
        ref_length = len(ref_seq)
        coverage_outfile = pathlib.Path(project_path, f"{run_name}_genome_coverage.csv")
        all_consensus_d = fasta_to_dct(all_samples_consens_seqs)
        ref_lookup_name = list(all_consensus_d.keys())[0]
        aligned_ref = all_consensus_d[ref_lookup_name]
        del all_consensus_d[ref_lookup_name]
        with open(coverage_outfile, 'w') as fh:
            fh.write("sample_name,genome_coverage\n")
            for v_name, v_seq in all_consensus_d.items():
                seq_coverage = 0
                for i, base in enumerate(v_seq.upper()):
                    if base != "-" and base != "N" and aligned_ref[i] != "-":
                        seq_coverage += 1
                percent_coverage = round((seq_coverage / ref_length) * 100, 2)
                fh.write(f"{v_name},{percent_coverage}\n")

    print("done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=Formatter)

    parser.add_argument('-in', '--project_path', type=str, default=None, required=True,
                        help='The path and name of the infile')
    parser.add_argument('-a', '--all_samples_consens_seqs', type=str, default=None, required=True,
                        help='The path for the outfile')
    parser.add_argument('-r', '--ref_seq', type=str, default=None, required=True,
                        help='The path for the outfile')
    parser.add_argument('-n', '--run_name', type=str, default=None, required=True,
                        help='The path for the outfile')

    args = parser.parse_args()
    project_path = args.project_path
    all_samples_consens_seqs = args.all_samples_consens_seqs
    ref_seq = args.ref_seq
    run_name = args.run_name

    main(project_path, all_samples_consens_seqs, ref_seq, run_name)