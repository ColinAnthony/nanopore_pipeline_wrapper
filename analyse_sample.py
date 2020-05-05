import argparse
import pathlib
import os,time
import json
import collections
import shutil
from src.misc_functions import try_except_continue_on_fail
from src.misc_functions import consensus_maker
from src.misc_functions import fasta_to_dct
from src.misc_functions import plot_primer_depth
from src.misc_functions import plot_depth
from src.misc_functions import py3_fasta_iter
from src.misc_functions import rename_fasta
from src.vcf_consensus import main as vcf_processing
from src.plot_vcf_qual_depth import main as vcf_plots
from src.plot_depths_qual import main as plot_depths_qual

__author__ = 'Colin Anthony'


class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
    pass


def main(infile, plot_folder, log_file, use_minmap2, chosen_ref_scheme, chosen_ref_scheme_bed_file, threads,
         msa_cons_also, min_depth, use_gaps, all_samples_consens_seqs):
    # force absolute file paths
    sample_fastq = pathlib.Path(infile).absolute()
    script_folder = pathlib.Path(__file__).absolute().parent
    if not sample_fastq.is_file():
        print(f"could not find the concatenated sample fastq file: {sample_fastq}\nskipping sample")
        with open(log_file, "a") as handle:
            handle.write(f"could not find the concatenated sample fastq file: {sample_fastq}\nskipping sample")
        return False

    # set the reference coordinates to use
    ref_name, ref_seq = list(py3_fasta_iter(chosen_ref_scheme))[0]
    ref_name = ref_name.split()[0]
    reference_slice = f"{ref_name}:0-{len(ref_seq)}"

    # set input and output file name
    sample_name = pathlib.Path(sample_fastq).stem
    sample_folder = pathlib.Path(sample_fastq).parent
    exp_folder = pathlib.Path(sample_fastq).parent.parent.parent
    fast5_folder = pathlib.Path(exp_folder, "fast5")
    seq_summary_file_name = ""
    for file in exp_folder.glob('sequencing_summary*.txt'):
        seq_summary_file_name = file
    seq_summary_file = pathlib.Path(seq_summary_file_name).resolve()
    artic_folder = pathlib.Path(sample_folder, "artic")
    artic_folder.mkdir(mode=0o777, parents=True, exist_ok=True)
    sam_name = pathlib.Path(sample_folder, sample_name + "_mapped.sam")
    trimmed_sam_file = pathlib.Path(sample_folder, sample_name + ".primerclipped.sam")
    trimmed_bam_file = pathlib.Path(sample_folder, sample_name + ".primerclipped.bam")
    sorted_trimmed_bam_file = pathlib.Path(sample_folder, sample_name + ".primerclipped_sorted.bam")
    bcftools_vcf_file = pathlib.Path(sample_folder, sample_name + "_bcftools.vcf")
    bcftools_cons_file = pathlib.Path(sample_folder, sample_name + "_consensus_bcftools.fasta")
    msa_fasta = pathlib.Path(sample_folder, sample_name + "_msa_from_bam_file.fasta")
    msa_cons = pathlib.Path(sample_folder, sample_name + "_msa_consensus.fasta")

    # make sure cwd is the sample folder, as some programs output to cwd
    os.chdir(sample_folder)

    print(f"\n\n________________\nStarting processing sample: {sample_name}\n\n________________\n")
    with open(log_file, "a") as handle:
        handle.write(f"\n\n________________\nStarting processing sample: {sample_name}\n\n________________\n")

    # start artic pipeline
    print(f"\n------->Starting Artic's pipeline in new window\n")
    artic_cmd = f"artic minion --normalise 200 --threads {threads} --scheme-directory ~/artic-ncov2019/primer_schemes "\
                f"--read-file {sample_fastq} --fast5-directory {fast5_folder} "\
                f"--sequencing-summary {seq_summary_file} nCoV-2019/V3 {sample_name}"
    try_except_continue_on_fail(
        f"gnome-terminal -- /bin/sh -c 'conda run -n artic-ncov2019 {artic_cmd}; exec bash'")
    last_file_made = pathlib.Path(sample_folder, sample_name + ".muscle.out.fasta")
    while pathlib.Path.exists(last_file_made) == False:
        time.sleep(5)
    else:
        time.sleep(2)
        all_files = os.listdir(sample_folder)

        # write consensus to master consensus file
        artic_cons_file = pathlib.Path(sample_folder, sample_name + ".consensus.fasta")
        artic_d = fasta_to_dct(artic_cons_file)
        with open(all_samples_consens_seqs, 'a') as fh:
            for name, seq in artic_d.items():
                fh.write(f">{name}\n{seq.replace('-', '')}\n")

        for filename in all_files:
            if os.path.isfile(filename) and not filename.endswith('.fastq'):
                file = os.path.join(sample_folder, filename)
                shutil.move(file, artic_folder)

    # start majority consensus pipeline
    if msa_cons_also:
        print(f"\n------->Starting majority consensus pipeline\n")
        if use_minmap2:
            # run read mapping using minimap
            print(f"\nrunning: minimap2 read mapping\n")
            minimap2_cmd = f"minimap2 -a -Y -t 8 -x ava-ont {chosen_ref_scheme} {sample_fastq} -o {sam_name} " \
                           f"2>&1 | tee -a {log_file}"
            print("\n", minimap2_cmd, "\n")
            with open(log_file, "a") as handle:
                handle.write(f"\nrunning: bwa read mapping\n")
                handle.write(f"{minimap2_cmd}\n")
            run = try_except_continue_on_fail(minimap2_cmd)
            if not run:
                return False
        else:
            # run read mapping using bwa
            print(f"\nrunning: bwa read mapping\n")
            bwa_cmd = f"bwa mem -t {threads} -x ont2d {chosen_ref_scheme} {sample_fastq} -o {sam_name} " \
                      f"2>&1 | tee -a {log_file}"
            print("\n", bwa_cmd,"\n")
            with open(log_file, "a") as handle:
                handle.write(f"\nrunning: bwa read mapping\n")
                handle.write(f"{bwa_cmd}\n")
            run = try_except_continue_on_fail(bwa_cmd)
            if not run:
                return False

        # remove primer sequences with custom script
        print(f"\nrunning: trim primer sequences from bam file\n")
        trim_script = pathlib.Path(script_folder, "src", "clip_primers_from_bed_file.py")
        trim_primer = f"python {trim_script} -in {sam_name} -o {trimmed_sam_file} " \
                      f"-b {chosen_ref_scheme_bed_file} 2>&1 | tee -a {log_file}"
        print("\n", trim_primer,"\n")
        with open(log_file, "a") as handle:
            handle.write(f"\nrunning: soft clipping primer sequences from bam file\n")
            handle.write(f"{trim_primer}\n")
        run = try_except_continue_on_fail(trim_primer)
        if not run:
            return False

        # convert sam to bam
        print(f"\nrunning: sam to bam conversion of trimmed file")
        sam_bam_cmd = f"samtools view -bS {trimmed_sam_file} -o {trimmed_bam_file} 2>&1 | tee -a {log_file}"
        print("\n", sam_bam_cmd,"\n")
        with open(log_file, "a") as handle:
            handle.write(f"\nrunning: sam to bam conversion\n")
            handle.write(f"{sam_bam_cmd}\n")
        run = try_except_continue_on_fail(sam_bam_cmd)
        if not run:
            return False

        # sort bam file
        print(f"\nrunning: sorting bam file")
        sort_sam_cmd = f"samtools sort -T {sample_name} {trimmed_bam_file} -o {sorted_trimmed_bam_file} " \
                       f"2>&1 | tee -a {log_file}"
        print("\n", sort_sam_cmd,"\n")
        with open(log_file, "a") as handle:
            handle.write(f"\nrunning: sorting bam file\n{sort_sam_cmd}\n")
        run = try_except_continue_on_fail(sort_sam_cmd)
        if not run:
            return False

        # index trimmed bam file
        print(f"\nrunning: indexing bam file")
        index_bam_cmd = f"samtools index {sorted_trimmed_bam_file} 2>&1 | tee -a {log_file}"
        print("\n", index_bam_cmd,"\n")
        with open(log_file, "a") as handle:
            handle.write(f"\nrunning: indexing bam file\n")
            handle.write(f"{index_bam_cmd}\n")
        run = try_except_continue_on_fail(index_bam_cmd)
        if not run:
            return False

        # make bcftools consensus
        # print(f"\nrunning: making consensuses sequence from bcftools\n")
        # min_base_qual = 30  # default=13
        # p_val_of_variant = 0.2  # default=0.5
        # bcf_vcf_cmd = f"bcftools mpileup --threads {threads} --max-depth 10000 --min-BQ {min_base_qual} -Oz " \
        #               f"-f {chosen_ref_scheme} {sorted_trimmed_bam_file} | bcftools call -c -p {p_val_of_variant} " \
        #               f"--ploidy 1 -Oz -o {bcftools_vcf_file} 2>&1 | tee -a {log_file}"
        # bcf_index_cmd = f"bcftools index {bcftools_vcf_file} 2>&1 | tee -a {log_file}"
        # bcf_cons_cmd = f"bcftools consensus -H A -f {chosen_ref_scheme} {bcftools_vcf_file} " \
        #                f"-o {bcftools_cons_file} 2>&1 | tee -a {log_file}"
        # with open(log_file, "a") as handle:
        #     handle.write(f"\nrunning: making consensuses sequence from bcftools:\n")
        #     handle.write(f"{bcf_vcf_cmd}\n\n{bcf_index_cmd}\n\n{bcf_cons_cmd}\n")
        # run = try_except_continue_on_fail(bcf_vcf_cmd)
        # if not run:
        #     return False
        # run = try_except_continue_on_fail(bcf_index_cmd)
        # if not run:
        #     return False
        # run = try_except_continue_on_fail(bcf_cons_cmd)
        # if not run:
        #     return False

        # rename the fasta header to the sample name
        # rename_fasta(bcftools_cons_file, sample_name, "bcftools_cons")
        # bcf_cons_d = fasta_to_dct(bcftools_cons_file)

        # write consensus to master consensus file
        # with open(all_samples_consens_seqs, 'a') as fh:
        #     for name, seq in bcf_cons_d.items():
        #         fh.write(f">{name}\n{seq.replace('-', '')}\n")

        # # generate manual vcf consensus and seq depth + qual output
        # depth_qual_outfile = vcf_processing(bcftools_vcf_file, min_depth, sample_folder)
        # vcf_plots(depth_qual_outfile, plot_folder)

        # get json dump of reads and primer pairs
        json_file = list(pathlib.Path(sample_folder).glob("*read_primer_pair_lookup.json"))[0]
        if not json_file.is_file():
            print("the json file containing primer pair depth info was not found")
        with open(str(json_file), 'r') as jd:
            read_primer_pairs_dct = json.load(jd)

        primer_pair_depth_outfile = pathlib.Path(plot_folder, sample_name + "_per_primer_depth.png")

        primer_pairs = []
        primers_depth = []
        for primer_pair, names_list in read_primer_pairs_dct.items():
            primers_depth.append(len(names_list))
            primer_pairs.append(primer_pair)

        max_depth = max(primers_depth)
        percent_primers_depth = [round(val / max_depth * 100, 2) for val in primers_depth]
        primers_and_depths = zip(primer_pairs, primers_depth)

        plot_primer_depth(primer_pairs, primers_depth, percent_primers_depth,
                          sample_name, primer_pair_depth_outfile)


        # convert bam file to a mutli fasta alignment
        print(f"\nrunning: making consensuses sequence from bam to MSA with jvarkit\n")

        sam4web = pathlib.Path(script_folder, "jvarkit", "dist", "sam4weblogo.jar")
        msa_from_bam = f"java -jar {sam4web} -r '{reference_slice}' -o {msa_fasta} " \
                       f"{sorted_trimmed_bam_file} 2>&1 | tee -a {log_file}"
        print(msa_from_bam)

        with open(log_file, "a") as handle:
            handle.write(f"\nrunning: making consensuses sequence from bam to MSA with jvarkit\n")
            handle.write(f"{msa_from_bam}\n")
        run = try_except_continue_on_fail(msa_from_bam)
        if not run:
            return False

        # convert multi fasta alignment to consensus sequence
        fasta_msa_d = fasta_to_dct(msa_fasta)

        if len(fasta_msa_d) == 0:
            print(f"{sam_name} alignment had no sequences\nskipping to next sample\n")
            with open(log_file, "a") as handle:
                handle.write(f"{sam_name} alignment had no sequences\nskipping to next sample\n")
            return False

        # set minimum depth for calling a position in the consensus sequence per primer region
        positional_depth = collections.defaultdict(int)
        for (primerpair, depth) in primers_and_depths:
            start_pos = int(primerpair.split("_")[0])
            end_pos = int(primerpair.split("_")[1])
            for i in range(start_pos, end_pos + 1):
                positional_depth[str(i).zfill(4)] += depth

        # build the consensus sequence
        try:
            cons, depth_profile = consensus_maker(fasta_msa_d, positional_depth, min_depth, use_gaps)
        except IndexError as e:
            with open(log_file, "a") as handle:
                handle.write(f"\nNo MSA made from Bam file\nno reads may have been mapped\n{e}\n")
        else:
            with open(msa_cons, 'w') as handle:
                handle.write(f">{sample_name}\n{cons}\n")

            # write consensus to master consensus file
            with open(all_samples_consens_seqs, 'a') as fh:
                fh.write(f">{sample_name}\n{cons.replace('-', '')}\n")

            # plot depth for sample
            depth_list = depth_profile["non_gap"]
            depth_outfile = pathlib.Path(plot_folder, sample_name + "_sequencing_depth.png")
            plot_depth(depth_list, sample_name, depth_outfile)

    print(f"Completed processing sample: {sample_name}\n\n")
    with open(log_file, "a") as handle:
        handle.write(f"\n\n________________\nCompleted processing sample: {sample_name}\n\n________________\n")

    print("done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='This script runs the read mapping, plotting and consensus generation'
                                                 'for a sample',
                                     formatter_class=Formatter)

    parser.add_argument('-in', '--infile', type=str, default=None, required=True,
                        help='The path and name of the sample fastq file')
    parser.add_argument('-pf', '--plot_folder', type=str, default=None, required=True,
                        help='The path to where the plots will be written')
    parser.add_argument('-lf', '--log_file', type=str, default=None, required=True,
                        help='The name and path for the logfile')
    parser.add_argument("-mm", "--use_minmap2", default=False, action="store_true",
                        help="use minimap2 instead of bwa to map reads to reference", required=False)
    parser.add_argument('-rs', '--chosen_ref_scheme', type=str, default=None, required=True,
                        help='The path and name of the reference scheme fasta file')
    parser.add_argument('-bf', '--chosen_ref_scheme_bed_file', type=str, default=None, required=True,
                        help='The path and name of the reference scheme bed file')
    parser.add_argument("-t", "--threads", type=int, default=8,
                        help="The number of threads to use for bwa, nanopolish etc...", required=False)
    parser.add_argument("-m", "--msa_cons_also", default=False, action="store_true",
                        help="Also generate consensus from MSA", required=False)
    parser.add_argument("-d", "--min_depth", type=int, default=100, help="The minimum coverage to call a position in "
                                                                         "the MSA to consensus", required=False)
    parser.add_argument("-ug", "--use_gaps", default=False, action="store_true",
                        help="use gap characters when making the consensus sequences", required=False)
    parser.add_argument('-ac', '--all_samples_consens_seqs', type=str, default=None, required=True,
                        help='The path and name of the file to contain consensus sequences from all samples')

    args = parser.parse_args()
    infile = args.infile
    plot_folder = args.plot_folder
    log_file = args.log_file
    use_minmap2 = args.use_minmap2
    chosen_ref_scheme = args.chosen_ref_scheme
    chosen_ref_scheme_bed_file = args.chosen_ref_scheme_bed_file
    threads = args.threads
    msa_cons_also = args.msa_cons_also
    min_depth = args.min_depth
    use_gaps = args.use_gaps
    all_samples_consens_seqs = args.all_samples_consens_seqs

    main(infile, plot_folder, log_file, use_minmap2, chosen_ref_scheme,
         chosen_ref_scheme_bed_file, threads, msa_cons_also, min_depth, use_gaps, all_samples_consens_seqs)
