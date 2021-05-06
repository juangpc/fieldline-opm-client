import threading, queue
import time

q = queue.Queue(5)

def worker():
    while True:
        item = q.get()
        print(f'Working on {item} ...')
        time.sleep(1)
        print(f'Finished {item}')
        q.task_done()

# turn-on the worker thread
threading.Thread(target=worker, daemon=True).start()

# send thirty task requests to the worker
for item in range(30):
    print(f'About to send item: {item}')
    q.put(item)
    print(f'Finished sending item: {item}')
print('All task requests sent', end='')

# block until all tasks are done
q.join()
print('All work completed\n')
