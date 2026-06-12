import os
from tkinter import Tk, filedialog

n_sub = int(input('Subject number: '))

sub = "S" + f"{n_sub:03}"

Tk().withdraw()
folder = filedialog.askdirectory()
file_list = os.listdir(folder)
print('Selected folder: ' + folder)
print('File names changes:')

if len(file_list) != 30:
    exit()
    
# ORDEN ORIGINAL
"""order = [
    (1,1,1), (1,1,2), (1,1,3), (1,1,4), (1,1,5), #BLOCK A 1
    (2,1,1), (2,1,2), (2,1,3), (2,1,4), (2,1,5), #BLOCK B 2
    (1,2,1), (1,2,2), (1,2,3), (1,2,4), (1,2,5), #BLOCK C 3
    (2,2,1), (2,2,2), (2,2,3), (2,2,4), (2,2,5), #BLOCK D 4
    (1,3,1), (1,3,2), (1,3,3), (1,3,4), (1,3,5), #BLOCK E 5
    (2,3,1), (2,3,2), (2,3,3), (2,3,4), (2,3,5)  #BLOCK F 6
]"""

"""
1:DISTAL    ,   1:One F     ,   1:0 angle
2:PROXIMAL  ,   2:Two F     ,   2:45 angle
            ,   3:Full G    ,   3:90 angle
                            ,   4:135 angle
                            ,   5:180 angle
"""

order = [
    (1,3,1), (1,3,2), (1,3,3), (1,3,4), (1,3,5), #BLOCK E 5
    (1,1,1), (1,1,2), (1,1,3), (1,1,4), (1,1,5), #BLOCK A 1
    (2,2,1), (2,2,2), (2,2,3), (2,2,4), (2,2,5), #BLOCK D 4
    (2,1,1), (2,1,2), (2,1,3), (2,1,4), (2,1,5), #BLOCK B 2
    (1,2,1), (1,2,2), (1,2,3), (1,2,4), (1,2,5), #BLOCK C 3
    (2,3,1), (2,3,2), (2,3,3), (2,3,4), (2,3,5),  #BLOCK F 6
]

for n, file in enumerate(file_list):
    i, j, k = order[n]
    new_name = f"{sub}_{i}{j}{k}.otb+"
    os.rename(os.path.join(folder, file), os.path.join(folder, new_name))
    print(file + ' -> ' + new_name)
