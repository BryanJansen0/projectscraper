db.dirty.updateMany(
  {},
  [
    {
      $set: {
        "detailed.titleModule.tradeCount": {
          $convert: {
            input: {
              $replaceAll: {
                input: {
                  $rtrim: {
                    input: "$detailed.titleModule.formatTradeCount",
                    chars: "+",
                  },
                },
                find: ",",
                replacement: "",
              },
            },
            to: "int",
          },
        },
      },
    },
  ],
  { multi: true }
);
