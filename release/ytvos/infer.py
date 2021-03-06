import argparse
import logging
import yaml
from pathlib import Path

from script_utils.common import common_setup

from release.helpers.misc import subprocess_call
from release.ytvos.compute_flow import link_splits


def get_config_ckpt(model_dir, step):
    config = Path(model_dir) / 'config_and_args.pkl'
    model = Path(model_dir) / 'ckpt' / f'model_step{step}.pth'
    return config, model


def main():
    # Use first line of file docstring as description if it exists.
    parser = argparse.ArgumentParser(
        description=__doc__.split('\n')[0] if __doc__ else '',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config', default=Path('./release/config.yaml'))
    parser.add_argument(
        '--without-ytvos-train',
        action='store_true',
        help=("By default, we infer with model that was trained on YTVOS. "
              "For fair evaluation of generalization, we use a model without "
              "YTVOS training in our manuscript. Set this to True to use "
              "the model without YTVOS training."))

    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.load(f)

    args = parser.parse_args()
    output_dir = Path(config['ytvos']['output_dir']) / 'detections'
    if args.without_ytvos_train:
        output_dir = output_dir / 'without_ytvos'
    else:
        output_dir = output_dir / 'with_ytvos'
    output_dir.mkdir(exist_ok=True, parents=True)
    common_setup(__file__, output_dir, args)

    detectron_dir = (
        Path(__file__).resolve().parent.parent.parent / 'detectron_pytorch')

    split_dirs = link_splits(config)
    for split in config['ytvos']['splits']:
        image_dir = split_dirs[split][0]
        flow_dir = Path(config['ytvos']['output_dir']) / 'flow' / split

        if args.with_ytvos_train:
            joint_config, joint_model = get_config_ckpt(
                config['model']['joint']['dir'],
                config['model']['joint']['step'])
        else:
            joint_config, joint_model = get_config_ckpt(
                config['model']['joint_no_ytvos']['dir'],
                config['model']['joint_no_ytvos']['step'])
        appearance_config, appearance_model = get_config_ckpt(
            config['model']['appearance']['dir'],
            config['model']['appearance']['step'])

        cmd = ['python', 'tools/infer_simple.py']
        args = [
            '--cfg', joint_config,
            '--num_classes', 2,
            '--load_ckpt', joint_model,
            '--load_appearance_ckpt', appearance_model,
            '--set', 'MODEL.MERGE_WITH_APPEARANCE.ENABLED', 'True',
            '--image_dirs', image_dir, flow_dir,
            '--input_type', 'rgb', 'flow',
            '--save_images', False,
            '--output_dir', output_dir / split,
            '--quiet',
            '--recursive'
        ]
        subprocess_call(cmd + args, cwd=str(detectron_dir))


if __name__ == "__main__":
    main()