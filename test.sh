#此处指定待评估的agent模型和日期
agent=/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae_nav.pt
date=2023-06-20

# # Clean
# python main.py \
#     -o storage/robothor-pointnav-rgb-rdmae-ddppo-eval \
#     -exp pointnav_robothor_vanilla_rgb_rdmae_ddppo \
#     -b projects/robustnav/experiments/eval \
#     -c $agent \
#     -t $date \
#     -et rnav_pointnav_vanilla_rgb_rdmae_ddppo_clean \
#     -s 12345 \
#     -e \
#     -tsg 0

# # (Defocus Blur, Motion Blur, Spatter, Low Lighting, Speckle Noise)
# for CORR in Defocus_Blur Lighting Speckle_Noise Spatter Motion_Blur
# do
#     python main.py \
#         -o storage/robothor-pointnav-rgb-rdmae-ddppo-eval \
#         -exp pointnav_robothor_vanilla_rgb_rdmae_ddppo \
#         -b projects/robustnav/experiments/eval \
#         -c $agent \
#         -t $date \
#         -et rnav_pointnav_vanilla_rgb_rdmae_ddppo_"$CORR"_s5 \
#         -s 12345 \
#         -e \
#         -tsg 0 \
#         -vc $CORR \
#         -vs 5
# done

# Lower-FOV
python main.py \
    -o storage/robothor-pointnav-rgb-rdmae-ddppo-eval \
    -exp pointnav_robothor_vanilla_rgb_rdmae_ddppo_fov \
    -b projects/robustnav/experiments/eval \
    -c $agent \
    -t $date \
    -et rnav_pointnav_vanilla_rgb_rdmae_ddppo_fov \
    -s 12345 \
    -e \
    -tsg 0

# Camera-Crack
python main.py \
    -o storage/robothor-pointnav-rgb-rdmae-ddppo-eval \
    -exp pointnav_robothor_vanilla_rgb_rdmae_ddppo_cam_crack \
    -b projects/robustnav/experiments/eval \
    -c $agent \
    -t $date \
    -et rnav_pointnav_vanilla_rgb_rdmae_ddppo_cam_crack \
    -s 12345 \
    -e \
    -tsg 0