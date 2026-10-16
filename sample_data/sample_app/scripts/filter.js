const data = msg.payload;

const objects = data.objects;

const uniqueCategories = new Set(Array.from((function* () { for (const key in objects) yield objects[key].category; })()));

const objectPerCategory = {};

for (const category of uniqueCategories) {
  objectPerCategory[category] = 0;
  for (const key in objects) {
    const object = objects[key];
    if (object.category !== category) continue;
    objectPerCategory[category] += 1;
  }
}

delete msg.payload.objects;
delete msg.payload.scene_rate;
delete msg.payload.rate;
msg.payload.objectPerCategory = objectPerCategory;

return msg;