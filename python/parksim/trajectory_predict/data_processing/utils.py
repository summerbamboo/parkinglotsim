import numpy as np
from typing import List
import cv2
import PIL
import traceback

from parksim.spot_detector.detector import LocalDetector

from dlp.dataset import Dataset
from dlp.visualizer import SemanticVisualizer

class TransformerDataProcessor(object):
    """
    Extract features for IRL
    """
    def __init__(self, ds: 'Dataset'):
        """
        Instantiate the feature extractor
        """
        self.ds = ds
        self.vis = SemanticVisualizer(ds, steps=1)

        self.spot_detector = LocalDetector(spot_color_rgb=(0, 255, 0))
        self.agent_detector = LocalDetector(spot_color_rgb=(255, 255, 0))
    
    def get_instance_index(self, inst_token: str, agent_token: str) -> int:
        """
        get the index of the specified instance relative to the lifetime of its agent
        """
        instances_agent_is_in = self.ds.get_agent_instances(agent_token)
        instance_tokens_agent_is_in = [instance['instance_token'] for instance in instances_agent_is_in]
        return instance_tokens_agent_is_in.index(inst_token), len(instance_tokens_agent_is_in)-1
    
    def filter_instances(self, frame_token: str, stride: int, history: int, future: int) -> List[str]:
        """
        return list of valid (having enough historical data) instances in this frame
        """
        frame = self.ds.get('frame', frame_token)

        filtered_tokens = []
        token_indices = []

        for inst_token in frame['instances']:
            instance = self.ds.get('instance', inst_token)
            agent = self.ds.get('agent', instance['agent_token'])
            if agent['type'] not in {'Pedestrian', 'Undefined'}:
                try:
                    if self.ds.get_inst_mode(inst_token) != 'incoming':
                        continue
                    current_inst_idx, max_idx = self.get_instance_index(inst_token, instance['agent_token'])
                    if current_inst_idx < stride * (history-1) or max_idx < current_inst_idx + stride * future:
                        continue
                    filtered_tokens.append(inst_token)
                    token_indices.append(current_inst_idx)
                except Exception as err:
                    print("==========\nError occured for instance %s" % inst_token)
                    traceback.print_exc()
        return filtered_tokens, token_indices

    def _get_corners(self, spot):
        return cv2.boxPoints(spot)
    
    def label_target_spot(self, inst_token: str, inst_centric_view: np.array, r=1.25) -> np.array:
        """
        Returns image frame with target spot labeled
        """
        all_spots = self.spot_detector.detect(inst_centric_view)

        traj = self.vis.dataset.get_future_traj(inst_token)
        instance = self.ds.get('instance', inst_token)
        current_state = np.array([instance['coords'][0], instance['coords'][1], instance['heading'], instance['speed']])
        for spot in all_spots:
            spot_center_pixel = np.array(spot[0])
            spot_center = self.vis.local_pixel_to_global_ground(current_state, spot_center_pixel)
            dist = np.linalg.norm(traj[:, 0:2] - spot_center, axis=1)
            if np.amin(dist) < r:
                inst_centric_view_copy = inst_centric_view.copy()
                corners = self._get_corners(spot)
                img_draw = PIL.ImageDraw.Draw(inst_centric_view_copy)  
                img_draw.polygon(corners, fill ="purple", outline ="purple")
                return inst_centric_view_copy
        
        return inst_centric_view
