import numpy as np


def get_pose(sim, handle, reference):
    """Return position and rotation matrix in the same reference frame."""
    matrix = np.array(sim.getObjectMatrix(handle, reference), dtype=float)
    matrix = matrix.reshape(3, 4)
    return matrix[:, 3], matrix[:, :3]


def get_jacobian(sim, joints, reference, end_point):
    """Calculate the geometric Jacobian of the UR5 end point."""
    end_position, end_rotation = get_pose(sim, end_point, reference)
    jacobian = np.zeros((6, 6))

    for column, joint in enumerate(joints):
        joint_position, joint_rotation = get_pose(sim, joint, reference)
        joint_axis = joint_rotation[:, 2]
        jacobian[:3, column] = np.cross(
            joint_axis, end_position - joint_position
        )
        jacobian[3:, column] = joint_axis

    return jacobian, end_position, end_rotation


def rotation_error(target_rotation, current_rotation):
    """Return a small-angle rotation error vector."""
    error_rotation = target_rotation @ current_rotation.T
    error = 0.5 * np.array(
        [
            error_rotation[2, 1] - error_rotation[1, 2],
            error_rotation[0, 2] - error_rotation[2, 0],
            error_rotation[1, 0] - error_rotation[0, 1],
        ]
    )
    return error


def sysCall_init():
    sim = require('sim')

    # The controller writes joint positions directly.
    sim.setBoolParam(sim.boolparam_dynamics_handling_enabled, False)

    # World frame is the ground reference (z = 0).
    self.reference = -1
    self.robot = sim.getObject('/UR5')

    path = '/UR5'
    self.joints = []
    for _ in range(6):
        path += '/joint'
        self.joints.append(sim.getObject(path))
        path += '/link'

    self.end_point = sim.getObject(path + '/EndPoint')
    self.target = sim.getObject('/Cuboid')

    # Start from the pose already saved in the scene.
    # Do not add an artificial shoulder/elbow offset: it can put the arm
    # below the floor before the IK loop even starts.
    self.q = np.array(
        [sim.getJointPosition(joint) for joint in self.joints],
        dtype=float,
    )

    self.max_step = 0.04
    self.damping = 0.08
    self.position_gain = 0.7
    self.rotation_gain = 0.5

    # A 50 mm cube is on the floor.  Move the tool to its top centre,
    # not to the centre of the cube, so the tool does not enter the floor.
    self.cube_half_height = 0.025


def sysCall_actuation():
    sim = require('sim')

    target_position, target_rotation = get_pose(
        sim, self.target, self.reference
    )
    target_position = (
        target_position + target_rotation[:, 2] * self.cube_half_height
    )

    jacobian, end_position, end_rotation = get_jacobian(
        sim,
        self.joints,
        self.reference,
        self.end_point,
    )

    position_error = target_position - end_position
    orientation_error = rotation_error(target_rotation, end_rotation)
    error = np.concatenate(
        [
            self.position_gain * position_error,
            self.rotation_gain * orientation_error,
        ]
    )

    # Damped least-squares inverse of the Jacobian.
    identity = np.eye(6)
    joint_step = jacobian.T @ np.linalg.solve(
        jacobian @ jacobian.T + self.damping**2 * identity,
        error,
    )

    step_size = np.linalg.norm(joint_step)
    if step_size > self.max_step:
        joint_step *= self.max_step / step_size

    self.q += joint_step
    for joint, angle in zip(self.joints, self.q):
        sim.setJointPosition(joint, float(angle))

    position_mm = np.linalg.norm(position_error) * 1000
    rotation_deg = np.degrees(np.linalg.norm(orientation_error))
    print('position: %.2f mm, rotation: %.2f deg' % (
        position_mm,
        rotation_deg,
    ))
