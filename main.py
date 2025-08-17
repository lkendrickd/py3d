"""
Main entry point for the 3D voxel world.
"""
import pygame
import numpy as np
import ctypes
import math
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_CULL_FACE,
    GL_BACK, GL_CCW, GL_TRIANGLES, glEnable, glCullFace, glFrontFace,
    glClearColor, glClear, glDrawArrays, glBindVertexArray
)

from config.settings import *
from engine.shader import Shader
from engine.camera import Camera
from engine.math_utils import perspective
from world.world_manager import WorldManager


def main():
    # Initialize Pygame
    pygame.init()
    
    # Auto-detect native resolution
    info = pygame.display.Info()
    WINDOW_WIDTH = info.current_w
    WINDOW_HEIGHT = info.current_h
    print(f"Detected native resolution: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    
    # Set OpenGL attributes before creating the display
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_COMPATIBILITY)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    pygame.display.gl_set_attribute(pygame.GL_SWAP_CONTROL, 1)  # Enable VSync
    
    # Set up display
    pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.DOUBLEBUF | pygame.OPENGL)
    pygame.display.set_caption("GPU Voxel World")
    
    # Lock cursor to window
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)
    
    # Enable depth testing and face culling
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    glCullFace(GL_BACK)
    glClearColor(0.53, 0.81, 0.92, 1.0)  # Sky blue
    
    # Create shader program
    shader = Shader(VERTEX_SHADER, FRAGMENT_SHADER)
    
    # Create camera
    camera = Camera()
    
    # Create world manager for dynamic chunk loading
    world_manager = WorldManager()
    
    # Load initial chunks around spawn point (small area first)
    print("Generating initial world...")
    initial_chunks = world_manager.load_initial_chunks(camera.position)
    print(f"Initial world generated: {initial_chunks} chunks")
    
    # Matrices
    model = np.eye(4, dtype=np.float32)
    projection = perspective(math.radians(60), WINDOW_WIDTH / WINDOW_HEIGHT, 0.1, 1000.0)
    
    # Main loop
    clock = pygame.time.Clock()
    running = True
    frame_count = 0
    fps_history = []
    target_fps = 60
    
    while running:
        dt = clock.tick(target_fps) / 1000.0
        fps = clock.get_fps()
        frame_count += 1
        
        # Track FPS for adaptive performance
        fps_history.append(fps)
        if len(fps_history) > 60:  # Keep last 60 frames
            fps_history.pop(0)
        
        avg_fps = sum(fps_history) / len(fps_history) if fps_history else 60
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type == pygame.MOUSEMOTION:
                dx, dy = event.rel
                camera.process_mouse(dx, dy)
        
        # Handle keyboard input
        keys = pygame.key.get_pressed()
        camera.process_keyboard(keys, dt)
        
        # Adaptive update frequency based on performance
        update_interval = 15  # Default
        if avg_fps < 30:
            update_interval = 25  # Slower updates, but still frequent
            world_manager.frame_budget_ms = 1.5  # Slightly increased budget
            world_manager.max_chunks_per_frame = 1  # Ensure at least one chunk can be processed
        elif avg_fps > 55:
            update_interval = 8   # Faster updates if FPS is excellent
            world_manager.frame_budget_ms = 4.0  # Increase budget significantly
            world_manager.max_chunks_per_frame = 2  # Allow more aggressive processing
        else:
            world_manager.frame_budget_ms = 2.0  # Default budget
            world_manager.max_chunks_per_frame = 1  # Normal processing
        
        # Update world based on camera position (adaptive frequency)
        if frame_count % update_interval == 0:
            print(f"Frame {frame_count}: Calling world_manager.update with camera position {camera.position}")
            world_manager.update(camera.position)
        
        # Force chunk cleanup every 60 frames regardless of movement
        if frame_count % 60 == 0:
            player_chunk_x, player_chunk_z = world_manager.get_chunk_coords(camera.position[0], camera.position[2])
            world_manager.unload_distant_chunks(player_chunk_x, player_chunk_z)
        
        # Clear screen
        glClearColor(0.53, 0.81, 0.92, 1.0)  # Sky blue
        glClear(int(GL_COLOR_BUFFER_BIT) | int(GL_DEPTH_BUFFER_BIT))
        
        # Use shader
        shader.use()
        
        # Set up matrices
        view_matrix = camera.get_view_matrix()
        proj_matrix = projection
        
        shader.set_mat4("model", model.flatten())
        shader.set_mat4("view", view_matrix.flatten())
        shader.set_mat4("projection", proj_matrix.flatten())
        
        # Lighting
        time_of_day = pygame.time.get_ticks() / 1000.0
        sun_angle = time_of_day * 0.05
        light_dir = np.array([math.sin(sun_angle), math.cos(sun_angle), 0.3], dtype=np.float32)
        shader.set_vec3("lightDir", light_dir)
        shader.set_vec3("viewPos", camera.position)
        shader.set_float("ambientStrength", 0.3)
        
        # Get visible chunks and render them with adaptive performance optimization
        visible_chunks = world_manager.get_visible_chunks(camera.position)
        chunks_rendered = 0
        
        # Always process completed chunks with minimal impact
        completed_chunks = world_manager.process_completed_chunks()
        
        # Adaptive rendering based on FPS and recent chunk processing
        if avg_fps < 30:
            max_chunks_to_render = min(len(visible_chunks), 20)  # Very conservative
        elif avg_fps < 45:
            max_chunks_to_render = min(len(visible_chunks), 40)  # Moderate
        else:
            max_chunks_to_render = min(len(visible_chunks), 60)  # More reasonable maximum
        
        for i, chunk in enumerate(visible_chunks):
            if i >= max_chunks_to_render:
                break
            chunk.render()
            chunks_rendered += 1
        
        # Swap buffers
        pygame.display.flip()
        
        # Enhanced window title with more info (update less frequently for performance)
        if frame_count % 30 == 0:  # Update title every 30 frames instead of every frame
            active_threads = len([t for t in world_manager.generation_threads if t.is_alive()])
            queue_size = world_manager.chunk_queue.qsize() + world_manager.priority_queue.qsize()
            generating_count = len(world_manager.generating_chunks)
            
            pygame.display.set_caption(
                f"GPU Voxel World - FPS: {fps:.0f} | "
                f"Chunks: {len(world_manager.chunks)} | "
                f"Rendered: {chunks_rendered} | "
                f"Queue: {queue_size} | "
                f"Generating: {generating_count} | "
                f"Threads: {active_threads} | "
                f"Pos: ({camera.position[0]:.1f}, {camera.position[1]:.1f}, {camera.position[2]:.1f})"
            )
    
    # Cleanup
    world_manager.cleanup()
    pygame.quit()


if __name__ == "__main__":
    main()