@interface Hello
{
}
+ classMethod;
+ classMethod2;
- objMethod1;
- objMethod2;
@end

@interface World
{
    Hello* world;
}
- (Hello*) world;
- (void) setWorld:(Hello*) world;
@end

@interface World2
{

}
- (World*) world2;
- (void) setWorld2:(World*) world2;
@end
