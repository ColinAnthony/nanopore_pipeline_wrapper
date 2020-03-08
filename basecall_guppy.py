import argparse
import pathlib
from src.misc_functions import try_except_continue_on_fail
import os, time
import shutil

__author__ = 'Colin Anthony'


class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
    pass


def main(inpath, guppy_path, outpath, gpu_threads, bascall_mode, real_time):
    # force absolute file paths
    inpath = pathlib.Path(inpath).absolute()
    outpath = pathlib.Path(outpath).absolute()
    if pathlib.Path.exists(outpath):
        shutil.rmtree(outpath)
    guppy_path = pathlib.Path(guppy_path).absolute()
    guppy_basecaller = pathlib.Path(guppy_path, "guppy_basecaller")
    cuda_device = "CUDA:0"
    config_option = ["dna_r9.4.1_450bps_fast.cfg ", "dna_r9.4.1_450bps_hac.cfg"]
    config = config_option[bascall_mode]
    if gpu_threads == 0:
        gpu_settings = ""
    else:
        gpu_settings = f"--gpu_runners_per_device {gpu_threads}  --num_callers 4 -x 'auto' "  # --device {cuda_device}
    if real_time:

        projectpath = inpath.parent
        basecalling_folder = pathlib.Path(projectpath, "basecalling")
        basecalling_folder.mkdir(mode=0o777, parents=True, exist_ok=True)
        temp_folder = pathlib.Path(projectpath, "temp")
        temp_folder.mkdir(mode=0o777, parents=True, exist_ok=True)
        resume = ""
        w = 0
        while w == 0:

            fast5files = sorted(os.listdir(inpath), key=lambda y: os.path.getmtime(os.path.join(inpath, y)))
            print(fast5files)
            firstlength = len(fast5files)
            if firstlength > 10:
                x = 10
            else:
                time.sleep(10)
                fast5files = sorted(os.listdir(inpath), key=lambda y: os.path.getmtime(os.path.join(inpath, y)))
                print(fast5files)
                secondlength = len(fast5files)
                if firstlength < secondlength:
                    x = len(fast5files)
                else:
                    x = len(fast5files)
                    w = 1

            for filename in fast5files[0:x]:
                file = os.path.join(inpath, filename)
                shutil.move(file, basecalling_folder)

            guppy_basecall_cmd = f"{str(guppy_basecaller)} -i {basecalling_folder} -r -s {outpath} -c {config} " \
                                 f"--compress_fastq --records_per_fastq 4000 --qscore_filtering 7 {resume}" \
                                 f"{gpu_settings}"

            run = try_except_continue_on_fail(guppy_basecall_cmd)
            if run:
                print("basecalling batch of 50 files")
            else:
                print("basecalling failed")

            for filename in os.listdir(basecalling_folder):
                file = os.path.join(basecalling_folder, filename)
                shutil.move(file, temp_folder)
            resume = '--resume '
        os.rmdir(inpath)
        os.rename(temp_folder, inpath)
        os.rmdir(basecalling_folder)

        return True

    else:
        guppy_basecall_cmd = f"{str(guppy_basecaller)} -i {inpath} -r -s {outpath} -c {config} " \
                             f"--compress_fastq --records_per_fastq 4000 --qscore_filtering 7 " \
                             f"{gpu_settings}"

        run = try_except_continue_on_fail(guppy_basecall_cmd)

        if run:
            print("basecalling completed\n")
        else:
            print("basecalling failed")

        return run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=Formatter)

    parser.add_argument('-in', '--inpath', type=str, default=None, required=True,
                        help='The path to the fast5 folder')
    parser.add_argument('-p', '--guppy_path', type=str, default=None, required=True,
                        help='The path to guppy exexutable')
    parser.add_argument('-o', '--outpath', type=str, default=None, required=True,
                        help='The path for the outfile')
    parser.add_argument("-g", "--gpu_threads", type=int, default=4,
                        help="The number of gpu threads to use, use '0' if no gpu available", required=False)
    parser.add_argument('-b', '--bascall_mode', type=int, choices=[0, 1], default=0, required=False,
                        help='0 = Fast mode\n'
                             '1 = high accuracy mode')
    parser.add_argument("-rt", "--real_time", default=False, action="store_true",
                        help="start basecalling fast5 files in batches during sequencing", required=False)

    args = parser.parse_args()
    inpath = args.inpath
    guppy_path = args.guppy_path
    outpath = args.outpath
    gpu_threads = args.gpu_threads
    bascall_mode = args.bascall_mode
    real_time = args.real_time

    main(inpath, guppy_path, outpath, gpu_threads, bascall_mode, real_time)
