# the-goodies

## Smart Home Knowledge Graph Distributed MCP Library for Swift iOS and Python Backend

A standalone, reusable Swift/Python MCP server library optimized for knowledge graphs representing homes, rooms, devices, and their relationships. Uses the Inbetweenies protocol for distributed synchronization between WildThing (Swift) and FunkyGibbon (Python) components.

Based on a discussion with Claude about how to approach this problem, the [initial plan document](homegraph_mcp_library_initial_plan.md) was created and saved here, ready for an agent swarm to implement it.

The first use of this project is to provide the storage layer and interface protocol between the iOS/Swift front end http://github.com/adrianco/c11s-house-ios that is currently in active development, waiting for this project to be functional and ready to integrate, and the Python backend http://github.com/adrianco/consciousness which was a first pass proof of concept prototype that will be discarded and re-written from scratch once this project is ready.

Naming scheme based on BBC TV comedy show The Goodies who had some "hit singles" in the 1970s, since Python is a reference to Monty Python... and lots of libraries have stupid names and I don't have anyone telling me what I can call things.
