import os
from tkinter import Tk, filedialog

n_sub = int(input('Subject number: '))
n_cam = int(input('Camera number [1-5]: '))

sub = "S" + f"{n_sub:03}"
letters = ['A', 'B', 'C', 'D', 'E']
cam = "cam" + letters[n_cam - 1]

Tk().withdraw()
folder = filedialog.askdirectory()
file_list = os.listdir(folder)
print('Selected folder: '+folder)
print('File names changes:')

# !=31 TOMANDO EN CUENTA LOS ARCHIVOS DE CALIBRACION QUE VA UNO POR CADA CAM.
if len(file_list) != 31:
    exit()

file_name_format = lambda i, j, k: f"{sub}_{i}{j}{k}-{cam}.mp4" if i + j + k > 0 else f"{sub}_calib-{cam}.mp4"

# ORDEN ORIGINAL
"""order = [
    #(0,0,0),
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
# ORDEN RANDOMIZADO PARA PRUEBA PILOTO 
order = [
    (0,0,0),
    (1,3,1), (1,3,2), (1,3,3), (1,3,4), (1,3,5), #BLOCK E 5
    (1,1,1), (1,1,2), (1,1,3), (1,1,4), (1,1,5), #BLOCK A 1
    (2,2,1), (2,2,2), (2,2,3), (2,2,4), (2,2,5), #BLOCK D 4
    (2,1,1), (2,1,2), (2,1,3), (2,1,4), (2,1,5), #BLOCK B 2
    (1,2,1), (1,2,2), (1,2,3), (1,2,4), (1,2,5), #BLOCK C 3
    (2,3,1), (2,3,2), (2,3,3), (2,3,4), (2,3,5),  #BLOCK F 6
]

for n, file in enumerate(file_list):
    i, j, k = order[n]
    new_name = file_name_format(i, j, k)
    os.rename(os.path.join(folder, file), os.path.join(folder, new_name))
    print(file+' -> '+new_name)