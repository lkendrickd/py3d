"""
Mathematical utilities for 3D rendering.
"""
import numpy as np
import math


def look_at(eye, center, up):
    """Create a look-at view matrix"""
    f = center - eye
    f = f / np.linalg.norm(f)
    
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    
    u = np.cross(s, f)
    
    result = np.eye(4, dtype=np.float32)
    result[0, 0] = s[0]
    result[1, 0] = s[1]
    result[2, 0] = s[2]
    result[0, 1] = u[0]
    result[1, 1] = u[1]
    result[2, 1] = u[2]
    result[0, 2] = -f[0]
    result[1, 2] = -f[1]
    result[2, 2] = -f[2]
    result[3, 0] = -np.dot(s, eye)
    result[3, 1] = -np.dot(u, eye)
    result[3, 2] = np.dot(f, eye)
    
    return result


def perspective(fov, aspect, near, far):
    """Create a perspective projection matrix"""
    f = 1.0 / math.tan(fov / 2.0)
    nf = 1.0 / (near - far)
    
    result = np.zeros((4, 4), dtype=np.float32)
    result[0, 0] = f / aspect
    result[1, 1] = f
    result[2, 2] = (far + near) * nf
    result[2, 3] = -1.0
    result[3, 2] = 2.0 * far * near * nf
    
    return result
