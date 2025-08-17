"""
Camera system for first-person controls.
"""
import pygame
import numpy as np
import math
from engine.math_utils import look_at
from config.settings import CHUNK_SIZE, RENDER_DISTANCE


class Camera:
    def __init__(self):
        self.position = np.array([CHUNK_SIZE * RENDER_DISTANCE // 2, 35.0, CHUNK_SIZE * RENDER_DISTANCE // 2], dtype=np.float32)
        self.yaw = -90.0
        self.pitch = 0.0
        self.speed = 15.0
        self.sensitivity = 0.3
        self.update_vectors()
    
    def update_vectors(self):
        """Update camera direction vectors based on yaw and pitch"""
        # Calculate front vector
        front = np.array([
            math.cos(math.radians(self.yaw)) * math.cos(math.radians(self.pitch)),
            math.sin(math.radians(self.pitch)),
            math.sin(math.radians(self.yaw)) * math.cos(math.radians(self.pitch))
        ], dtype=np.float32)
        self.front = front / np.linalg.norm(front)
        
        # Calculate right and up vectors
        self.right = np.cross(self.front, np.array([0, 1, 0], dtype=np.float32))
        self.right /= np.linalg.norm(self.right)
        self.up = np.cross(self.right, self.front)
        self.up /= np.linalg.norm(self.up)
    
    def process_keyboard(self, keys, delta_time):
        """Process keyboard input for movement"""
        velocity = self.speed * delta_time
        
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.position += self.front * velocity
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.position -= self.front * velocity
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.position -= self.right * velocity
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.position += self.right * velocity
        if keys[pygame.K_SPACE] or keys[pygame.K_e]:
            self.position[1] += velocity
        if keys[pygame.K_LSHIFT] or keys[pygame.K_q]:
            self.position[1] -= velocity
    
    def process_mouse(self, xoffset, yoffset):
        """Process mouse movement for looking around"""
        xoffset *= self.sensitivity
        yoffset *= self.sensitivity
        
        self.yaw += xoffset
        self.pitch -= yoffset
        
        # Constrain pitch
        self.pitch = np.clip(self.pitch, -89.0, 89.0)
        
        self.update_vectors()
    
    def get_view_matrix(self):
        """Get the view matrix for rendering"""
        target = self.position + self.front
        return look_at(self.position, target, self.up)
