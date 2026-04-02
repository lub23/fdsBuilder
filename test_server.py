from bfds_viewer import BlenderClient

client = BlenderClient()
print("Starting Blender server...")
ok = client.start_server(9876)
print(f"Server started: {ok}")

if ok:
    result = client.execute("print(bpy.context.scene.name)")
    print(f"Execute result: {result}")
    client.stop()
