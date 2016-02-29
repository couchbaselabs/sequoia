FILE=$1
for host in $( grep ip: $FILE | awk -F ":" '{print $2}' ); do
  addr=$(getent hosts $host | cut -d' ' -f1)
  echo $host."->".$addr
  sed -i "s/$host/$addr/g" $FILE
done