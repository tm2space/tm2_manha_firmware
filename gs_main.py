from manha.gs import ManhaGS
import asyncio
import machine
 
def main():
    gs = ManhaGS()
    try:
        gs.run()
    except Exception as e:
        print(f"Exception in `main.py`: {e}")
    finally:
        machine.reset()
        
while True:
    main()

