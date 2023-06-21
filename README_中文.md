# [Regularized Denoising Masked Visual Pretraining for Robust Embodied PointGoal Navigation](https://www.mdpi.com/1424-8220/23/7/3553)



# 整体结构

![](/home/pengjie/projects/RDMAE_Nav/assets/overall.png)



# 环境安装

NVIDIA GeForce RTX 3060、python3.6、torch1.10.2+cu113

1. 首先安装[Anaconda](https://docs.anaconda.com/anaconda/install/linux/)

2. 创建conda虚拟环境

   ```
   conda env create --file robustnav.yml --name <ENV-NAME>
   
   e.g. conda env create --file robustnav.yml --name rdmaenav
   ```

3. 激活虚拟环境

   ```
   conda activate <ENV-NAME>
   ```



# 训练

## 设置

需要在“allenact/embodiedai/preprocessors/vit.py ”中指定预训练的视觉模块

```
e.g. 
pretrain_path = "/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae.pth"
```

### 启动训练

运行下面的命令开始训练导航agent

```
bash train.sh
```

## 说明

```
python main.py \
    -o storage/robothor-pointnav-rgb-rdmae-ddppo \
    -exp pointnav_robothor_vanilla_rgb_rdmae_ddppo \
    -b projects/robustnav/experiments/train \
    -s 12345 \
    -et rnav_pointnav_vanilla_rgb_rdmae_ddppo_clean
    
#参数说明
-o:		指定模型及log保存位置
-exp:	指定实验配置，与-b一同构成任务文件及路径
-b:		指定任务文件夹路径
-s:		指定随机数种子
-et:	保存tensorboard的文件夹名称
```



# 测试

## 设置

预训练模型包含两部分：visual module和policy module

1. 在"allenact/embodiedai/preprocessors/vit.py"中的pretrain_path处指定预训练visual module的路径

   ```
   e.g. 
   pretrain_path = "/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae.pth"
   ```

2. 在"test.sh"中的agent处指定预训练policy module的路径

   ```
   e.g.
   agent=/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae_nav.pt
   ```

## 启动测试

运行下面的命令开始测试导航agent

```
bash test.sh
```

## 说明

测试包含clean和其余7项视觉扰动的测试，测试结果保存在"storage/robothor-pointnav-rgb-rdmae-ddppo-eval"中



# 可视化

## 设置

在./projects/tutorials/running_inference_tutorial.py、running_inference_tutorial_fov.py和running_inference_tutorial_cam_crack.py中指定需要可视化任务

```
viz_ep_ids：		指定top-down轨迹需要可视化的episode
viz_video_ids：	指定第一视角导航动图需要可视化的episode
```

## 启动可视化

```
bash viz.sh
```

## 说明

可视化的结果保存在“storage/robothor-pointnav-rgb-rdmae-ddppo-eval”的tensorboard文件中

**第一视角动图**

![](/home/pengjie/projects/RDMAE_Nav/assets/video_example.gif)

**top-down轨迹**

![](/home/pengjie/projects/RDMAE_Nav/assets/scene_viz.png)

![](/home/pengjie/projects/RDMAE_Nav/assets/coor_viz.png)



# 注意事项

需要联网才能渲染出UI界面，因此在训练/测试时**需要联网**，训练/测试启动后可以断网



# 致谢

代码大部分参考了https://github.com/allenai/robustnav，感谢！



# 其他

本项目由[Daniel Peng](https://github.com/dniwsac)完成



# 引用

如果您觉得此项目对您有帮助，请考虑引用文章：

```
@article{peng2023regularized,
  title={Regularized Denoising Masked Visual Pretraining for Robust Embodied PointGoal Navigation},
  author={Peng, Jie and Xu, Yangbin and Luo, Luqing and Liu, Haiyang and Lu, Kaiqiang and Liu, Jian},
  journal={Sensors},
  volume={23},
  number={7},
  pages={3553},
  year={2023},
  publisher={MDPI}
}
```







