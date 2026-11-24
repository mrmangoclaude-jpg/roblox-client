local out={}
local folder=Instance.new("Folder")
local propertySignal=folder:GetPropertyChangedSignal("Name")
out.signalIdentity=propertySignal==folder:GetPropertyChangedSignal("Name")
out.signalType=typeof(propertySignal)
local changed=0
local connection=propertySignal:Connect(function() changed+=1 end)
folder.Name="Folder"
folder.Name="Renamed"
out.eventsDeferred=changed==0
local attrs=0
local attrConnection=folder:GetAttributeChangedSignal("Count"):Connect(function()attrs+=1 end)
folder:SetAttribute("Count",1);folder:SetAttribute("Count",1);folder:SetAttribute("Count",nil)
local once=0
local onceConnection=folder.ChildAdded:Once(function(child)if child.Parent==folder then once+=1 end end)
local child1=Instance.new("Folder",folder)
local child2=Instance.new("Folder",folder)
local cancelled=0
local disconnected=folder:GetPropertyChangedSignal("Archivable"):Connect(function()cancelled+=1 end)
folder.Archivable=false;disconnected:Disconnect();folder.Archivable=true
local spawned=false
local resumed=false
local taskThread=task.spawn(function()
 spawned=true
 local elapsed=task.wait(0.002)
 resumed=elapsed>=0
end)
out.spawnImmediate=spawned
out.threadType=typeof(taskThread)
local deferred=false
task.defer(function()deferred=true end)
local never=false
local cancelThread=task.delay(0.01,function()never=true end)
task.cancel(cancelThread)
task.wait(0.025)
out.propertyChangedOnce=changed==1
out.attributeChangedTwice=attrs==2
out.onceCalledOnce=once==1 and not onceConnection.Connected
out.disconnectedCancelled=cancelled==0
out.yieldResumed=resumed
out.deferRan=deferred
out.delayCancelled=not never
task.delay(0.002,function()Instance.new("Folder",folder).Name="WaitedChild"end)
local waited=folder.ChildAdded:Wait()
out.waitEventValue=waited.Name=="WaitedChild" and waited.Parent==folder
local yieldingCallback=false
folder:GetAttributeChangedSignal("Yield"):Once(function()
 task.wait(0.002)
 yieldingCallback=true
end)
folder:SetAttribute("Yield",true)
-- Give the yielding Once callback enough scheduler time on slower hosts.
-- The assertion is that it eventually resumes, not that it does so in 10 ms.
task.wait(0.05)
out.yieldingCallback=yieldingCallback
local destroying=0
local destroyedConnection=child1.Destroying:Connect(function()destroying+=1 end)
child1:Destroy()
out.destroyDisconnect=not destroyedConnection.Connected
task.wait()
out.destroyEventRan=destroying==1
connection:Disconnect();attrConnection:Disconnect()
out.manualDisconnect=not connection.Connected
local instanceAttr=Instance.new("Folder",folder)
instanceAttr:SetAttribute("Self",instanceAttr)
local attrClone=instanceAttr:Clone()
out.attributeRefNotRemapped=attrClone:GetAttribute("Self")==instanceAttr
attrClone:Destroy()
folder:Destroy()
return out
