"""
Game settings and constants.
"""
import numpy as np
import math

# Screen settings - will be updated to native resolution
SCREEN_W, SCREEN_H = 1024, 768  # Default fallback

# Voxel world parameters
CHUNK_SIZE = 16
WORLD_HEIGHT = 64
RENDER_DISTANCE = 20  # Reduced from 24 to 20 for better performance
PRELOAD_DISTANCE = 25  # Reduced from 30 to 25 for memory management
UNLOAD_DISTANCE = 25   # Reduced from 35 to 25 for aggressive cleanup

# Camera and rendering parameters
FOV = math.radians(60)  # Field of view in radians
NEAR_PLANE = 0.1
FAR_PLANE = 1500.0  # Increased for longer render distance

# Lighting settings
LIGHT_DIRECTION = np.array([-0.3, -0.7, -0.2], dtype=np.float32)
LIGHT_COLOR = np.array([1.0, 1.0, 0.9], dtype=np.float32)
AMBIENT_COLOR = np.array([0.3, 0.3, 0.4], dtype=np.float32)

# Fog settings
FOG_START = 150.0  # Adjusted for longer render distance
FOG_END = 600.0    # Adjusted for 24 chunk render distance
FOG_COLOR = np.array([0.5, 0.8, 1.0], dtype=np.float32)

# Block types
BLOCK_AIR = 0
BLOCK_GRASS = 1
BLOCK_DIRT = 2
BLOCK_STONE = 3
BLOCK_WATER = 4
BLOCK_SAND = 5
BLOCK_WOOD = 6
BLOCK_LEAVES = 7

# Block colors (RGB normalized to 0-1)
BLOCK_COLORS = np.array([
    [0.0, 0.0, 0.0],          # Air (not rendered)
    [0.13, 0.55, 0.13],       # Grass - green
    [0.40, 0.26, 0.13],       # Dirt - brown
    [0.50, 0.50, 0.50],       # Stone - gray
    [0.25, 0.64, 0.87],       # Water - blue
    [0.93, 0.79, 0.69],       # Sand - beige
    [0.55, 0.27, 0.07],       # Wood - brown
    [0.13, 0.55, 0.13],       # Leaves - green
], dtype=np.float32)

# Shader sources
VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 normal;
layout(location = 2) in vec3 color;

out vec3 fragColor;
out vec3 fragNormal;
out vec3 fragPos;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main() {
    fragPos = vec3(model * vec4(position, 1.0));
    fragNormal = mat3(transpose(inverse(model))) * normal;
    fragColor = color;
    gl_Position = projection * view * vec4(fragPos, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330 core
in vec3 fragColor;
in vec3 fragNormal;
in vec3 fragPos;

out vec4 outColor;

uniform vec3 lightDir;
uniform vec3 viewPos;
uniform float ambientStrength;

void main() {
    // Ambient lighting
    vec3 ambient = ambientStrength * fragColor;
    
    // Diffuse lighting
    vec3 norm = normalize(fragNormal);
    vec3 lightDirNorm = normalize(-lightDir);
    float diff = max(dot(norm, lightDirNorm), 0.0);
    vec3 diffuse = diff * fragColor;
    
    // Simple fog effect for distance
    float distance = length(viewPos - fragPos);
    float fogFactor = exp(-distance * 0.02);
    fogFactor = clamp(fogFactor, 0.0, 1.0);
    
    vec3 result = ambient + diffuse;
    result = mix(vec3(0.53, 0.81, 0.92), result, fogFactor); // Sky blue fog
    
    outColor = vec4(result, 1.0);
}
"""
