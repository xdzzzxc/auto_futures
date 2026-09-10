from public import print_context, shared_data as sd
for key in dir(sd):
    print(getattr(sd,key))
# print(dir(sd))

if __name__ == '__main__':
    pass