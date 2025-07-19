import os

folder_path = "server/datasets/project/images" 
# folder_path = "client/gopro_captures" 


# Count only files ending with .jpg or .JPG
jpg_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.jpg')]

print(f"Number of .JPG files: {len(jpg_files)}")
