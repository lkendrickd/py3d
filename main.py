"""
Main entry point for the 3D voxel world - FIXED VERSION.
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
    pygame.display.gl_set_attribute(pygame.GL_SWAP_CONTROL, 1 if VSYNC else 0)
    
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
    
    # FIX: Track performance metrics
    low_fps_counter = 0
    last_chunk_count = 0

    while running:
        dt = clock.tick(target_fps) / 1000.0
        fps = clock.get_fps()
        frame_count += 1
        
        # Track FPS for adaptive performance
        fps_history.append(fps)
        if len(fps_history) > 60:  # Keep last 60 frames
            fps_history.pop(0)
        
        avg_fps = sum(fps_history) / len(fps_history) if fps_history else 60
        
        # FIX: Track low FPS occurrences
        if fps < 30:
            low_fps_counter += 1
        else:
            low_fps_counter = max(0, low_fps_counter - 1)

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                # FIX: Add debug key to show stats
                elif event.key == pygame.K_F3:
                    print(f"\n=== Debug Stats ===")
                    print(f"Chunks loaded: {len(world_manager.chunks)}")
                    print(f"Chunks generating: {len(world_manager.generating_chunks)}")
                    print(f"Mesh build queue: {world_manager.chunks_to_build_mesh.qsize()}")
                    print(f"Cleanup queue: {len(world_manager.chunks_to_cleanup)}")
                    print(f"FPS: {fps:.1f} (avg: {avg_fps:.1f})")
                    print(f"Camera pos: {camera.position}")
                    print(f"Camera dir: {camera.front}")
                    print("==================\n")
            elif event.type == pygame.MOUSEMOTION:
                dx, dy = event.rel
                camera.process_mouse(dx, dy)

        # Handle keyboard input
        keys = pygame.key.get_pressed()
        camera.process_keyboard(keys, dt)
        
        # FIX: Adaptive update frequency based on performance and chunk status
        update_interval = 10  # Default

        if low_fps_counter > 10:  # Consistently low FPS
            update_interval = 30
            world_manager.max_chunks_per_frame = 1
            world_manager.max_mesh_builds_per_frame = 2
        elif avg_fps < 45:
            update_interval = 20
            world_manager.max_chunks_per_frame = 2
            world_manager.max_mesh_builds_per_frame = 4
        elif avg_fps > 55:
            update_interval = 5
            world_manager.max_chunks_per_frame = 4
            world_manager.max_mesh_builds_per_frame = 10
        else:
            update_interval = 10
            world_manager.max_chunks_per_frame = 3
            world_manager.max_mesh_builds_per_frame = 8
        
        # FIX: Update world with camera direction for better prioritization
        if frame_count % update_interval == 0:
            world_manager.update(camera.position, camera.front)
        
        # FIX: More aggressive chunk management when chunk count changes
        current_chunk_count = len(world_manager.chunks)
        if current_chunk_count != last_chunk_count:
            if current_chunk_count > world_manager.max_chunks:
                # Force immediate cleanup if over limit
                excess = current_chunk_count - world_manager.max_chunks
                world_manager.force_cleanup_furthest_chunks(excess + 20)
            last_chunk_count = current_chunk_count

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

        # Render the world using the mesh batch
        world_manager.render_world()
        chunks_rendered = len(world_manager.chunks) # Approximate

        # Swap buffers
        pygame.display.flip()

        # Enhanced window title with more info (update less frequently for performance)
        if frame_count % 20 == 0:  # FIX: Update more frequently for better feedback
            active_threads = len([t for t in world_manager.generation_threads if t.is_alive()])
            queue_size = world_manager.chunk_queue.qsize() + world_manager.priority_queue.qsize()
            generating_count = len(world_manager.generating_chunks)
            mesh_queue = world_manager.chunks_to_build_mesh.qsize()

            # FIX: Show chunk limit warning
            chunk_warning = " [MAX!]" if len(world_manager.chunks) >= world_manager.max_chunks else ""

            pygame.display.set_caption(
                f"GPU Voxel World - FPS: {fps:.0f} (avg: {avg_fps:.0f}) | "
                f"Chunks: {len(world_manager.chunks)}/{world_manager.max_chunks}{chunk_warning} | "
                f"Visible: {chunks_rendered} | "
                f"Gen: {generating_count} | "
                f"Mesh: {mesh_queue} | "
                f"Pos: ({camera.position[0]:.0f}, {camera.position[1]:.0f}, {camera.position[2]:.0f})"
            )
    
    # Cleanup
    print("\nShutting down...")
    world_manager.cleanup()
    pygame.quit()


if __name__ == "__main__":
    main()