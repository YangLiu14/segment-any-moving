import argparse
import logging
import pathlib
import pickle

import pycocotools.mask as mask_util
import numpy as np
from scipy.optimize import linear_sum_assignment
from tqdm import tqdm

import utils.vis as vis
from utils.fbms import FbmsGroundtruth, get_tracks_text, masks_to_tracks


def process_sequences(fbms_dir, detectron_dir, output_dir):
    assert fbms_dir.exists()
    assert detectron_dir.exists()

    output_dir.mkdir(exist_ok=True)

    sequence_paths = list(fbms_dir.iterdir())
    sequence_names = [x.name for x in sequence_paths]

    output_paths = []
    for sequence, sequence_path in zip(tqdm(sequence_names), sequence_paths):
        groundtruth_path = sequence_path / 'GroundTruth'
        assert groundtruth_path.exists(), (
            'Path %s does not exists' % groundtruth_path)
        groundtruth = FbmsGroundtruth(groundtruth_path)
        frame_number_to_labels = groundtruth.frame_labels()
        detectron_paths = (detectron_dir / sequence).glob('*.pickle')
        detectron_paths = sorted(
            detectron_paths, key=lambda x: int(x.stem.split('_')[1]))

        final_masks = {}
        for frame_number, frame_labels in frame_number_to_labels.items():
            groundtruth_masks = []
            for color, region_id in groundtruth.color_to_region.items():
                if region_id == 0:
                    # ppms have full white (255 * 256**2 + 255 * 256 + 255)
                    # as background, pgms have 0 as background.
                    assert color == 16777215 or color == 0
                    continue  # Ignore background
                groundtruth_masks.append(frame_labels == region_id)

            detectron_path = detectron_paths[frame_number]
            assert detectron_path.exists(), (
                '%s does not exist.' % detectron_path)
            with open(detectron_path, 'rb') as f:
                data = pickle.load(f)
                _, predicted_masks, _, _ = vis.convert_from_cls_format(
                    data['boxes'], data['segmentations'], data['keypoints'])
                predicted_masks = mask_util.decode(predicted_masks)
                predicted_masks = [
                    predicted_masks[:, :, i]
                    for i in range(predicted_masks.shape[2])
                ]

            mask_distance = np.zeros(
                (len(groundtruth_masks), len(predicted_masks)))
            mask_distance = 1-mask_util.iou(
                [mask_util.encode(p) for p in predicted_masks],
                [mask_util.encode(np.asfortranarray(g.astype('uint8')))
                 for g in groundtruth_masks],
                pyiscrowd=np.zeros(len(groundtruth_masks)))

            # Array of length num_matches, containing tuples of
            # (predicted_mask_index, groundtruth_mask_index)
            assignments = list(zip(*linear_sum_assignment(mask_distance)))
            final_mask = np.zeros(groundtruth_masks[0].shape, dtype=np.uint8)
            if False:
                from matplotlib import pyplot as plt
                plt.close()
                _, ax = plt.subplots(len(assignments), 2)
                plt.suptitle('Frame %s' % frame_number)
            for predicted_mask_index, groundtruth_id in assignments:
                predicted_mask = predicted_masks[predicted_mask_index]
                final_mask[predicted_mask != 0] = groundtruth_id + 1
                if False:
                    ax[groundtruth_id, 0].imshow(groundtruth_masks[groundtruth_id])
                    ax[groundtruth_id, 0].title.set_text('Groundtruth')
                    ax[groundtruth_id, 1].imshow(predicted_mask)
                    ax[groundtruth_id, 1].title.set_text(
                        'Predicted; iou: %.4f' %
                        (1 - mask_distance[predicted_mask_index, groundtruth_id]))
            if False:
                plt.show()
            final_masks[frame_number] = final_mask
        tracks = masks_to_tracks(final_masks)
        tracks_str = get_tracks_text(tracks, groundtruth.num_frames)

        output_file = output_dir / (sequence + '.dat')
        output_paths.append(output_file)
        with open(output_file, 'w') as f:
            f.write(tracks_str)

    with open(output_dir / 'all_tracks.txt', 'w') as f:
        for output_path in output_paths:
            f.write(str(output_path.resolve()) + '\n')

    with open(output_dir / 'all_shots.txt', 'w') as f:
        f.write(str(len(sequence_paths)) + '\n')
        for sequence, sequence_path in zip(sequence_names, sequence_paths):
            groundtruth_path = sequence_path / 'GroundTruth' / (
                sequence + 'Def.dat')
            f.write(str(groundtruth_path.resolve()) + '\n')


def main():
    # Use first line of file docstring as description if it exists.
    parser = argparse.ArgumentParser(
        description=__doc__.split('\n')[0] if __doc__ else '',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('fbms_root')
    parser.add_argument('detectron_outputs',
                        help="""
                        Directory containing detectron outputs. Assumed to
                        contain TrainingSet/ and TestSet/ directories,
                        structured like
                        TrainingSet/<sequence>/<sequence>_<frame>.pickle, e.g.
                        TrainingSet/bear01/bear01_0000.pickle.""")
    parser.add_argument('output_dir')
    parser.add_argument(
        '--set', choices=['train', 'test', 'all'], default='all')
    args = parser.parse_args()

    output = pathlib.Path(args.output_dir)
    output.mkdir(exist_ok=True)

    logging.getLogger().setLevel(logging.INFO)
    logging.basicConfig(
        format='%(asctime)s.%(msecs).03d: %(message)s', datefmt='%H:%M:%S')

    fbms_root = pathlib.Path(args.fbms_root)
    assert fbms_root.exists()

    detectron_root = pathlib.Path(args.detectron_outputs)
    assert detectron_root.exists()

    use_train = args.set in ('train', 'all')
    use_test = args.set in ('test', 'all')

    if use_train:
        process_sequences(fbms_root / 'TrainingSet',
                          detectron_root / 'TrainingSet',
                          output / 'TrainingSet')

    if use_test:
        process_sequences(fbms_root / 'TestSet',
                          detectron_root / 'TestSet',
                          output / 'TestSet')


if __name__ == "__main__":
    main()